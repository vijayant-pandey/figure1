def test_verification_license_invalid_endpoint(client, headers):
    """
    Test what should be invalid models
    :param client:
    :param headers:
    :return:
    """
    # Test missing license number
    invalid_json = {
        'method': 'license',
        'user_uid': "test_user_uid",
        'license_school_code': "school_uuid",
        'license_country_code': "country_uuid",
        'graduation_year': 2020
    }
    response = client.post('/pro/v1/verification', headers=headers, json=invalid_json)
    assert response.status_code == 422


def test_verification_npi_model_invalid_endpoint(client, headers):
    invalid_json = {
        'method': 'npi',
        'user_uid': "test_user_uuid"
    }
    response = client.post('/pro/v1/verification', headers=headers, json=invalid_json)
    assert response.status_code == 422


def test_verification_photos_invalid_url_endpoint(client, headers):
    invalid_json = {
        'method': 'photo',
        'user_uid': "test_user_uid",
        'photos': ['Not a valid http string']
    }
    response = client.post('/pro/v1/verification', headers=headers, json=invalid_json)
    assert response.status_code == 422


def test_verification_photos_invalid_too_many_photos_endpoint(client, headers):
    invalid_json = {
        'method': 'photo',
        'user_uid': "test_user_uid",
        'photos': ['https://www.google.ca',
                   'https://www.google.ca',
                   'https://www.google.ca',
                   'https://www.google.ca',
                   'https://www.google.ca']
    }
    response = client.post('/pro/v1/verification', headers=headers, json=invalid_json)
    assert response.status_code == 422
