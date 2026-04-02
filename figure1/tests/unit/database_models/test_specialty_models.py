import uuid
import json
from figure1.tools.specialties import handle_json_upload
from figure1.common.models.db import ProfessionV2, UserProfession, SpecialtyV2, SpecialtyTreeV2
from figure1.common.types import ProfessionModel, UserProfessionV2Model, SpecialtyTreeModel


def test_user_profession(load_db, specialty_data):
    """
    Create a Profession Model and extract it through UserProfession
    :return:
    """
    p = ProfessionV2(profession_category='test_category',
                     specialty_uuid=uuid.uuid4(),
                     specialty_type='profession',
                     name='test_name',
                     label='test_label')
    p_o = p.as_object()
    assert isinstance(p_o, ProfessionModel)
    assert p_o.professionName == 'test_name'
    assert p_o.professionLabel == 'test_label'
    user_prof = UserProfession(user_uuid=uuid.uuid4(), profession_uuid=uuid.uuid4(), profession=p)
    assert isinstance(user_prof.as_object(), UserProfessionV2Model)
    u = user_prof.as_dict()


def test_add_profession():
    upload_struct = {
        "data": [
            {
                "profession_name": "Assistant Specialist",
                "profession_category": "Other HCP"
            }
        ]
    }
    handle_json_upload(data=upload_struct.get("data"), upload_type='profession')


def test_tree_exists(load_db, specialty_data):
    """
    Ensure that the tree and specialties created with csv files exist. The values here are taken from the csvs in
    the data directories.
    :param load_db:
    :return:
    """

    session = load_db
    p = session.query(ProfessionV2.specialty_uuid).filter(ProfessionV2.name == 'Medical Assistant').one()
    profession_uuid = p[0]
    s = session.query(SpecialtyV2.specialty_uuid).filter(SpecialtyV2.name == 'Cartoons').one()
    specialty_uuid = s[0]

    t = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.profession_uuid == profession_uuid,
                SpecialtyTreeV2.specialty_v2_uuid == specialty_uuid).one()
    model = SpecialtyTreeModel.from_orm(t).dict()
    assert model['onboardingDisplayName'] == 'Assistant'
    assert model['profileDisplayName'] == 'Cartoon|Assistant'
    assert model['caseCommentDisplayName'] == 'Internal Specialist'
