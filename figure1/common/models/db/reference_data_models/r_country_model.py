import uuid
from typing import Iterable
from sqlalchemy import Column, String, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, remote, foreign, backref
from sqlalchemy_utils import LtreeType, Ltree
from figure1.common.types import CountryModel
from figure1.core import Base, HasCreateUpdateDeleteTime


class Country(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_countries"

    country_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    name = Column(String(1024), default="", nullable=False, index=True)
    code = Column(String(32), default="", nullable=False, index=True)
    alpha_3 = Column(String(3), default="", nullable=False, index=True)
    type = Column(String(128), default="", nullable=False)
    path = Column(LtreeType, nullable=False)

    parent = relationship(
        'Country',
        primaryjoin=remote(path) == foreign(func.subpath(path, 0, -1)),
        backref=backref('regions', uselist=True, sync_backref=False),
        viewonly=True,
        sync_backref=False,
    )
    __table_args__ = (
        Index('ix_countries_path', path, postgresql_using="gist"),
    )

    @staticmethod
    def create_or_update(name, code, type, path_str, alpha_3="", skip_commit=False, session=None):
        path = Ltree(path_str)

        existing_item = session.query(Country) \
            .filter(Country.path == path) \
            .one_or_none()
        if existing_item:
            if existing_item.name != name:
                existing_item.name = name
            if existing_item.code != code:
                existing_item.code = code
            if existing_item.alpha_3 != alpha_3:
                existing_item.alpha_3 = alpha_3
            if existing_item.type != type:
                existing_item.type = type
            if existing_item.path != path:
                existing_item.path = path
            return existing_item

        c = Country()
        c.country_uuid = uuid.uuid4()
        c.name = name
        c.code = code
        c.alpha_3 = alpha_3
        c.type = type
        c.path = path

        session.add(c)

        if skip_commit:
            return c

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return c

    def as_dict(self):
        return {
            'countryUuid': str(self.country_uuid),
            'name': self.name,
            'code': self.code,
            'alpha3': self.alpha_3,
            'type': self.type,
            'path': self.path,
        }

    def as_object(self):
        return CountryModel.from_orm(self)

    def elasticsearch_dict(self):
        return CountryModel.from_orm(self).dict()

    @staticmethod
    def get_name_for_uuid(uuid, session=None):
        if not uuid:
            return None
        c = Country.q.get(uuid)
        if c is not None:
            return c.name
        return None

    @staticmethod
    def find_all_countries(session=None, supported_country_code=None) -> Iterable[CountryModel]:
        country_filter = [func.nlevel(Country.path) == 1]
        if supported_country_code:
            country_filter.append(Country.code == supported_country_code)
        for c in session.query(Country) \
                .filter(*country_filter) \
                .all():
            yield c.as_object()
