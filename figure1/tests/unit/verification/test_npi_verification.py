from figure1.common.utils import validate_npi


def test_npi_validation():
    valid_npi_numbers = ['1528350139', '1184682718', '1144600198', '1528099090']
    invalid_npi_numbers = ['1234567890', '234']
    for valid_num in valid_npi_numbers:
        assert validate_npi(npi=valid_num) is True
    for invalid_num in invalid_npi_numbers:
        assert validate_npi(npi=invalid_num) is False
