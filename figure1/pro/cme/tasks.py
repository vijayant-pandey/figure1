import datetime
import io
import logging
import os
import subprocess

from docxtpl import DocxTemplate

from figure1.common.types import CMETypes
from figure1.common.types import CMEContentPositionModel
from figure1.common.types import CmeDegreeTypeOptions
from figure1.configuration import app_settings
from figure1.core import TaskBase, celery_app
from figure1.common.models.db import CmeCertificateTemplate, \
    UserSpecialtyTreeV2, \
    User, \
    SpecialtyTreeV2, \
    CaseProgress, \
    Case
from figure1.common.utils import download_from_s3, cme_certificate_path
from figure1.common.utils import upload_to_s3
from figure1.exceptions import CertificateCreationError, S3Error, CertificateTemplateNotFound, CaseNotCompletedError

logger = logging.getLogger('figure1.cme')


def _convert_docx_to_pdf(docx_path, pdf_dir, pdf_path):
    with open(pdf_path, 'w+') as f:
        try:
            args = ['libreoffice', '--headless', '--convert-to', 'pdf', '--outdir', pdf_dir, docx_path]
            process = subprocess.run(args, stdout=f, stderr=subprocess.PIPE, timeout=30)
        except subprocess.TimeoutExpired as e:
            logger.exception('Failed to convert certificate to pdf, timeout reached')
            raise CertificateCreationError(msg='Failed to create the cme certificate, timeout reached') from e

    if process.stderr.decode():
        logger.error(f"Failed to convert certificate to pdf: {process.stderr.decode()}")
        raise CertificateCreationError(msg='Failed to convert certificate to pdf')


def _render_certificate(template_path: str,
                        user: User,
                        case: Case,
                        temp_dir: str,
                        degree_type: CmeDegreeTypeOptions) -> str:
    """
    Creates a PDF CME Certificate for a user based on a given template.  Supports docx templates.
    The template is downloaded from s3 and a certificate is created by substituting in user details
    :return:  The path to the created certificate
    """
    if case.feed_card:
        if case.feed_card.title:
            case_title = case.feed_card.title
        else:
            case_title = case.feed_card.caption
    else:
        case_title = str(case.case_uuid)
    render_dict = {
        "firstname": user.first_name,
        "lastname": user.last_name,
        "date": datetime.date.today().isoformat(),
        "casetitle": case_title
    }

    if isinstance(degree_type, str):
        render_dict.update({
            "degreetype": degree_type,
            "degreeType": degree_type,
        })

    elif isinstance(degree_type, CmeDegreeTypeOptions):
        render_dict.update({
            "degreetype": degree_type.value,
            "degreeType": degree_type.value,
        })

    else:
        render_dict.update({
            "degreetype": "",
            "degreeType": "",
        })

    docx_path = os.path.join(temp_dir, str(user.user_uuid) + ".docx")
    pdf_path = os.path.join(temp_dir, str(user.user_uuid) + ".pdf")

    try:
        s3_object = download_from_s3(path=template_path)
    except S3Error as e:
        logger.exception('Failed to download certificate template')
        raise CertificateCreationError(msg='Failed to download certificate template') from e

    buffer = io.BytesIO()
    buffer.write(s3_object.get('Body').read())
    try:
        doc = DocxTemplate(buffer)
        doc.render(render_dict)
        doc.save(docx_path)
        _convert_docx_to_pdf(docx_path=docx_path, pdf_dir=temp_dir, pdf_path=pdf_path)
        return pdf_path
    except ValueError as e:
        logger.exception('Failed to render a cme certificate')
        raise CertificateCreationError(msg='Failed to render a cme certificate') from e


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.upload_cme_certificate')
def upload_cme_certificate(self: TaskBase,
                           cme_content_position: CMEContentPositionModel):
    user = User.get_user_by_uuid(user_uuid=cme_content_position.userUuid, session=self.session, raise_exception=True)
    case = Case.get_case(case_uuid=cme_content_position.caseUuid, session=self.session, raise_exception=True)
    temp_dir = os.path.join('/tmp', user.user_uid)
    try:
        os.makedirs(temp_dir, exist_ok=True)
    except OSError:
        logger.exception(f"Failed to create temp dir %s", temp_dir)
        raise

    progress = self.session.query(CaseProgress).get((cme_content_position.caseUuid, user.user_uuid))
    if not progress or not progress.completed_at:
        raise CaseNotCompletedError(case_uuid=cme_content_position.caseUuid,
                                    user_uuid=user.user_uuid,
                                    msg=f'User {user.user_uuid} has not yet'
                                        f' completed case {cme_content_position.caseUuid}')

    template_path = None
    if cme_content_position.cmeType is CMETypes.CASE:
        template_path = app_settings.case_cme_template
    else:
        professions = self.session.query(SpecialtyTreeV2) \
            .join(UserSpecialtyTreeV2, UserSpecialtyTreeV2.tree_uuid == SpecialtyTreeV2.specialty_uuid) \
            .filter(UserSpecialtyTreeV2.user_uuid == user.user_uuid) \
            .all()
        for p in professions:
            t = self.session.query(CmeCertificateTemplate).get((cme_content_position.caseUuid, p.profession_uuid))
            if t:
                template_path = t.path
                break

    if template_path:
        temp_pdf = _render_certificate(template_path=template_path,
                                       user=user,
                                       case=case,
                                       temp_dir=temp_dir,
                                       degree_type=cme_content_position.degreeType)
        upload_path = cme_certificate_path(case_uuid=cme_content_position.caseUuid, user_uid=user.user_uid)
        upload_to_s3(source_path=temp_pdf, upload_path=upload_path)
    else:
        logger.exception("Could not find a certificate template")
        raise CertificateTemplateNotFound(case_uuid=cme_content_position.caseUuid,
                                          user_uuid=user.user_uuid,
                                          msg='Could not find a certificate template')
