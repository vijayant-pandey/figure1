def validate_npi(npi):
    """
    This is a implementation of the Luhn algorithm specific to the NPI number format. This ensures the npi
    itself is valid before saving and attempting to validate against the remote api.
    :param npi:
    :return:
    """

    def to_list(i):
        return [int(x) for x in str(i)]

    npi_list = to_list(npi)
    check_digit = npi_list[-1:]
    check_list = npi_list[:-1]
    count = 0
    total = 24
    for n in reversed(check_list):
        if not count % 2:
            for t in (to_list(n + n)):
                total += t
        else:
            for t in (to_list(n)):
                total += t
        count += 1
    cl = to_list(total)
    to_check = cl[-1:][0]
    if to_check:
        to_check = 10 - to_check
    return check_digit[0] == to_check
