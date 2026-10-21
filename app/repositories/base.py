from sqlmodel import Session


class BaseRepository:
    """Repositories flush but never commit. The service layer decides where a transaction ends."""

    def __init__(self, session: Session):
        self.session = session

    def add(self, entity):
        self.session.add(entity)
        self.session.flush()
        return entity

    def delete(self, entity) -> None:
        self.session.delete(entity)
        self.session.flush()
