from flask import request


def test_legacy_case_redirection(client, headers, test_legacy_case):
    valid_hello_link1 = "https://app.figure1.com/hello?t=WL3ek2DdE97e4BrIYVozcoha" \
                        "&r=aHR0cHMlM0ElMkYlMkZhcHAuZmlndXJlMS5jb20lMkZyZCUyRmltYWdlcyUyRjVk" \
                        "YTVmNWJhMDMxZjRlMWQwMDAzMmFlZA"
    response = client.post(f'/pro/v1/legacy/case_redirect', headers=headers, json={
        'url': valid_hello_link1
    })
    assert response.location == f'https://pro-dev.figure1.com/cases/{test_legacy_case.case_uuid}'
    assert response.status_code == 301

    valid_hello_link2 = "https://app.figure1.com/hello?r=aHR0cHMlM0ElMkYlMkZhcHAuZmlndXJlMS5jb" \
                        "20lMkZyZCUyRmltYWdlcyUyRjVkYTVmNWJhMDMxZjRlMWQwMDAzMmFlZA"
    response = client.post(f'/pro/v1/legacy/case_redirect', headers=headers, json={
        'url': valid_hello_link2
    })
    assert response.location == f'https://pro-dev.figure1.com/cases/{test_legacy_case.case_uuid}'
    assert response.status_code == 301

    invalid_hello_link = "https://app.figure1.com/hello?t=WL3ek2DdE97e4BrIYVozcoha&r=notvalid"
    response = client.post(f'/pro/v1/legacy/case_redirect', headers=headers, json={
        'url': invalid_hello_link
    })
    assert response.location == f'https://pro-dev.figure1.com/rfy'
    assert response.status_code == 301

    valid_rd_link = "https://app.figure1.com/rd/images/5da5f5ba031f4e1d00032aed?utm_medium=email"
    response = client.post(f'/pro/v1/legacy/case_redirect', headers=headers, json={
        'url': valid_rd_link
    })
    assert response.location == f'https://pro-dev.figure1.com/cases/{test_legacy_case.case_uuid}'
    assert response.status_code == 301

    invalid_rd_link = "https://app.figure1.com/rd/images/000000000000000000000001?utm_medium=email"
    response = client.post(f'/pro/v1/legacy/case_redirect', headers=headers, json={
        'url': invalid_rd_link
    })
    assert response.location == f'https://pro-dev.figure1.com/rfy'
    assert response.status_code == 301

    invalid_link_format = "https://app.figure1.com/rd/profile/5da5f5ba031f4e1d00032aed?utm_medium=email"
    response = client.post(f'/pro/v1/legacy/case_redirect', headers=headers, json={
        'url': invalid_link_format
    })
    assert response.location == f'https://pro-dev.figure1.com/rfy'
    assert response.status_code == 301
