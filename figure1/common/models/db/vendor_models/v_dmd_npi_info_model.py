import logging

from sqlalchemy import BigInteger
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID

from figure1.common.types.verification import DmdNpiDataModel
from figure1.core import Base, HasCreateUpdateTime

logger = logging.getLogger(__name__)


class DmdNpiInfo(Base, HasCreateUpdateTime):
    __tablename__ = 'v_dmd_npi_info'
    user_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)

    email = Column(Text, index=True, nullable=False)
    first_name = Column(Text, nullable=True)
    last_name = Column(Text, nullable=True)
    npi_number = Column(BigInteger, index=True, nullable=True)
    profession = Column(Text, nullable=True)
    specialty = Column(Text, nullable=True)
    subspecialty = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    state = Column(Text, nullable=True)
    practice_hospital = Column(Text, nullable=True)
    practice_location = Column(Text, nullable=True)
    graduation_date = Column(DateTime(timezone=True))
    school = Column(Text, nullable=True)

    dmd_hcp_type = Column(Text, nullable=True)
    dmd_dgid = Column(Text, nullable=True)
    dmd_firstname = Column(Text, nullable=True)
    dmd_lastname = Column(Text, nullable=True)
    dmd_degree = Column(Text, nullable=True)
    dmd_primary_specialty = Column(Text, nullable=True)
    dmd_specialty_long_description = Column(Text, nullable=True)
    dmd_npi = Column(BigInteger, index=True, nullable=True)
    dmd_state = Column(Text, nullable=True)

    @staticmethod
    def get_dmd_npi_info_by_email(email, session):
        return session.query(DmdNpiInfo).filter(DmdNpiInfo.email == email).one_or_none()

    @staticmethod
    def _generate_dmd_npi_info_instance(data_model: DmdNpiDataModel) -> 'DmdNpiInfo':
        new_dmd_npi_info = DmdNpiInfo()

        model_dict = data_model.dict(exclude_unset=True)
        for k in data_model.__fields_set__:
            if hasattr(new_dmd_npi_info, k):
                setattr(new_dmd_npi_info, k, model_dict[k])

        return new_dmd_npi_info

    @staticmethod
    def create(dmd_data_model: DmdNpiDataModel) -> 'DmdNpiInfo':
        return DmdNpiInfo._generate_dmd_npi_info_instance(data_model=dmd_data_model)
