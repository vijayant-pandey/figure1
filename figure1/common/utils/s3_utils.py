import boto3
import os
import logging

import hashlib

import botocore
import requests
from botocore.exceptions import NoCredentialsError, ClientError
from typing import BinaryIO

from figure1.configuration import app_settings
from figure1.exceptions import S3Error

read_only_logger = logging.getLogger('figure1.read_only_mode')

case_image_path = 'cases/images'
case_image_original_path = 'cases/images-original'
cme_certificate_templates_path = 'cases/certificate-templates'
dmd_data_path = 'dmd'


def cme_certificate_path(case_uuid, user_uid):
    CME_case_uuid = str(case_uuid)
    first_eight_letters_of_case_uuid = CME_case_uuid[0:8]
    cme_cert_name = f'CME_Certificate_{first_eight_letters_of_case_uuid}.pdf'
    return '/'.join(['users', 'certificates', user_uid, cme_cert_name])


def _create_s3_client():
    if 'AWS_ACCESS_KEY_ID' in os.environ:
        access = os.environ.get('AWS_ACCESS_KEY_ID')
        secret = os.environ.get('AWS_SECRET_ACCESS_KEY')

        if not secret:
            raise S3Error(msg='No AWS_SECRET_ACCESS_KEY defined')

        s3_client = boto3.client('s3',
                                 aws_access_key_id=access,
                                 aws_secret_access_key=secret)

        return s3_client
    else:
        return boto3.client('s3')


def generate_presigned_s3_get_object_url(path, expires_in=31536000):
    bucket = app_settings.s3_upload_bucket
    if not bucket:
        raise S3Error(msg='No bucket defined')

    try:
        s3_client = _create_s3_client()
        return s3_client.generate_presigned_url('get_object',
                                                Params={
                                                    'Bucket': bucket,
                                                    'Key': path,
                                                },
                                                ExpiresIn=expires_in)
    except Exception as e:
        logging.error(f"Failed to generate url {e}")
        raise


def generate_presigned_s3_upload_url(upload_path, expires_in=300, include_filename=False):
    """
    If include_filename is True, a POST presigned url structure is returned, otherwise, a PUT presigned
    url is returned which is just a url string
    :param upload_path: path to presign - if
    :param expires_in: time in seconds until expiry, defaults to 300 seconds or 5 minutes
    :param include_filename: Set to true to allow the uploaded filename to be the final key in the path
    :return:
    {
        "url": "s3 bucket url",
        "fields": {
            "AWSAccessKeyId": "",
            "key": "drafts/<user_uid>/<draft_uid>/${filename}",
            "policy": "",
            "signature": "v"
        }
    }
    or <url string>
    """
    bucket = app_settings.s3_upload_bucket
    if not bucket:
        raise S3Error(msg='No upload bucket defined')

    try:
        s3_client = _create_s3_client()
        if include_filename:
            upload_path = upload_path.strip('/')
            upload_path = upload_path + "/${filename}"
            return s3_client.generate_presigned_post(Bucket=bucket, Key=upload_path, ExpiresIn=expires_in)
        return s3_client.generate_presigned_url('put_object',
                                                Params={'Bucket': bucket,
                                                        'Key': upload_path,
                                                        'CacheControl': "max-age=31536000"
                                                        },
                                                ExpiresIn=expires_in
                                                )
    except Exception as e:
        logging.error(f"Failed to generate url {e}")
        raise


def upload_to_s3(source_path, upload_path):
    if app_settings.read_only_dev_mode:
        read_only_logger.warning(f"READ-ONLY MODE: Blocked upload_to_s3() operation for {upload_path}")
        return
        
    upload_url = generate_presigned_s3_upload_url(upload_path=upload_path)
    if os.path.exists(source_path):
        with open(source_path, mode='rb') as up_file:
            r = requests.put(upload_url, data=up_file.read())
            if r.status_code != 200:
                logging.error("Caught status %s", r.status_code)
                os.unlink(source_path)
                raise S3Error(msg=f'Failed to upload file: {r.content}')
        os.unlink(source_path)
    else:
        logging.error(f"Failed to find {source_path}")


def upload_stream_to_s3(upload_path, file_stream: BinaryIO):
    if app_settings.read_only_dev_mode:
        read_only_logger.warning(f"READ-ONLY MODE: Blocked upload_stream_to_s3() operation for {upload_path}")
        file_stream.close()
        return
        
    upload_url = generate_presigned_s3_upload_url(upload_path=upload_path)
    r = requests.put(upload_url, data=file_stream)
    if r.status_code >= 400:
        logging.error("Upload to S3 failed with status code %s", r.status_code)
    file_stream.close()


def delete_from_s3(path):
    if app_settings.read_only_dev_mode:
        read_only_logger.warning(f"READ-ONLY MODE: Blocked delete_from_s3() operation for {path}")
        return {'success': "delete blocked by read-only mode"}
        
    bucket = app_settings.s3_upload_bucket
    if not bucket:
        raise S3Error(msg='No bucket defined')

    try:
        s3_client = _create_s3_client()
        s3_client.delete_object(Bucket=bucket, Key=path)
    except ClientError as e:
        logging.error(f'Failed to delete s3 bucket={bucket} key={path}: {e}')
        raise S3Error(msg=f'Failed to delete s3 object')

    logging.info(f'Successfully deleted from s3: bucket={bucket}, key={path}')
    return {'success': "file deleted"}


def download_from_s3(path):
    bucket = app_settings.s3_upload_bucket
    if not bucket:
        raise S3Error(msg='No bucket defined')

    try:
        s3_client = _create_s3_client()
        return s3_client.get_object(Bucket=bucket,
                                    Key=path)
    except NoCredentialsError as nce:
        logging.error("AWS Credentials are not configured properly")
        raise
    except ClientError as e:
        logging.error(f"Generic exception while downloading file {e}")
        raise S3Error(msg=f'Failed to download s3 object')


def upload_image_to_s3(file, upload_dir, temp_dir):
    extension_pos = file.filename.rfind('.')
    file_extension = file.filename[extension_pos:]
    file_hash = hashlib.blake2s(file.read()).hexdigest()
    filename = file_hash + file_extension
    file.stream.seek(0)

    upload_path = f'{upload_dir}/{filename}'

    try:
        os.makedirs(temp_dir, exist_ok=True)
    except Exception as e:
        logging.error(f"Failed to create temp dir {temp_dir}: {e}")
        raise

    save_path = os.path.join(temp_dir, filename)
    try:
        file.save(save_path)
    except Exception as e:
        logging.error(f"Failed to save image: {e}")
        raise

    upload_to_s3(source_path=save_path, upload_path=upload_path)

    return {
        'upload_path': upload_path,
        'file_hash': file_hash,
        'filename': filename,
        'photo_url': app_settings.figure1_imgix_url + upload_path
    }


def move_s3_file(old_path, new_path) -> bool:
    if app_settings.read_only_dev_mode:
        read_only_logger.warning(f"READ-ONLY MODE: Blocked move_s3_file() operation from {old_path} to {new_path}")
        return False
        
    bucket = app_settings.s3_upload_bucket
    if not bucket:
        raise S3Error(msg='No bucket defined')

    s3_client = _create_s3_client()

    try:
        s3_client.copy_object(CopySource=bucket + '/' + old_path, Bucket=bucket, Key=new_path)
        s3_client.delete_object(Bucket=bucket, Key=old_path)
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return False
        raise

    return True


def check_s3_file_exists(path):
    s3_bucket = app_settings.s3_upload_bucket
    if not s3_bucket:
        raise S3Error(msg='No bucket defined')

    s3_client = _create_s3_client()

    try:
        s3_client.head_object(Bucket=s3_bucket, Key=path, )
        return True
    except botocore.exceptions.ClientError:
        return False
