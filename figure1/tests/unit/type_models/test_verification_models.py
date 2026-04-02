from figure1.common.types import UserVerificationPhotos


class UserSinglePhoto:
    verification_photo = 'http://www.google.ca'


class UserMultiplePhotos:
    verification_photo = 'http://www.google.ca'
    verification_photo2 = 'http://www.google.ca'


def test_multiple_photos():
    photos = UserVerificationPhotos.from_orm(UserMultiplePhotos())
    assert len(photos.verificationPhoto) == 2


def test_single_photo():
    photo = UserVerificationPhotos.from_orm(UserSinglePhoto())
    assert len(photo.verificationPhoto) == 1
