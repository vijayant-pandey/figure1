class SpecialtyError(Exception):
    def __init__(self, *args, **kwargs):
        self.specialty_uuid = kwargs.get('specialty_uuid')
        self.msg = kwargs.get('msg')

    def __str__(self):
        return f"Error while handling specialty uuid {self.specialty_uuid} error: {self.msg}"


class InvalidSpecialty(SpecialtyError):
    def __init__(self, *args, **kwargs):
        self.specialty_uuid = kwargs.get('specialty_uuid', None)
        self.msg = kwargs.get('msg', "Specialty uuid is invalid")

    def __str__(self):
        return f"Specialty uuid {self.msg} is invalid in this context - error: {self.msg}"


class InvalidProfession(SpecialtyError):
    def __init__(self, *args, **kwargs):
        self.specialty_uuid = kwargs.get('profession_uuid', None)
        self.msg = kwargs.get('msg', "Profession uuid is invalid")

    def __str__(self):
        return f"Profession uuid {self.msg} is invalid in this context - error: {self.msg}"
