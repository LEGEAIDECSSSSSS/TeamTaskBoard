from sqlmodel import col, func, select

from app.core.time import utcnow
from app.repositories.base import BaseRepository
from app.schemas.models.enums.role import OrgRole
from app.schemas.models.enums.status import InvitationStatus, MembershipStatus
from app.schemas.models.organisation import AuditLog, Invitation, Organisation, OrganisationMember
from app.schemas.models.team import Team, TeamMember
from app.schemas.models.user import User


class OrganisationRepository(BaseRepository):
    def get(self, organisation_id: int) -> Organisation | None:
        return self.session.get(Organisation, organisation_id)

    def active_membership(self, organisation_id: int, user_id: int) -> OrganisationMember | None:
        return self.session.exec(
            select(OrganisationMember).where(
                OrganisationMember.organisation_id == organisation_id,
                OrganisationMember.user_id == user_id,
                OrganisationMember.status == MembershipStatus.ACTIVE,
            )
        ).first()

    def any_membership(self, organisation_id: int, user_id: int) -> OrganisationMember | None:
        return self.session.exec(
            select(OrganisationMember).where(
                OrganisationMember.organisation_id == organisation_id, OrganisationMember.user_id == user_id
            )
        ).first()

    def memberships_for_user(self, user_id: int) -> list[tuple[OrganisationMember, Organisation]]:
        rows = self.session.exec(
            select(OrganisationMember, Organisation)
            .join(Organisation, col(Organisation.id) == col(OrganisationMember.organisation_id))
            .where(OrganisationMember.user_id == user_id, OrganisationMember.status == MembershipStatus.ACTIVE)
            .order_by(col(OrganisationMember.joined_at))
        ).all()
        return list(rows)

    def members(self, organisation_id: int) -> list[tuple[OrganisationMember, User]]:
        rows = self.session.exec(
            select(OrganisationMember, User)
            .join(User, col(User.id) == col(OrganisationMember.user_id))
            .where(
                OrganisationMember.organisation_id == organisation_id,
                OrganisationMember.status == MembershipStatus.ACTIVE,
            )
            .order_by(col(User.name))
        ).all()
        return list(rows)

    def active_owner_count(self, organisation_id: int) -> int:
        return self.session.exec(
            select(func.count(col(OrganisationMember.id))).where(
                OrganisationMember.organisation_id == organisation_id,
                OrganisationMember.role == OrgRole.OWNER,
                OrganisationMember.status == MembershipStatus.ACTIVE,
            )
        ).one()

    def team_counts(self, organisation_id: int) -> dict[int, int]:
        rows = self.session.exec(
            select(TeamMember.user_id, func.count(col(TeamMember.id)))
            .join(Team, col(Team.id) == col(TeamMember.team_id))
            .where(Team.organisation_id == organisation_id, col(TeamMember.left_at).is_(None))
            .group_by(TeamMember.user_id)
        ).all()
        return {user_id: count for user_id, count in rows}


class InvitationRepository(BaseRepository):
    def get(self, invitation_id: int) -> Invitation | None:
        return self.session.get(Invitation, invitation_id)

    def pending_for_org(self, organisation_id: int) -> list[Invitation]:
        return list(
            self.session.exec(
                select(Invitation)
                .where(
                    Invitation.organisation_id == organisation_id,
                    Invitation.status == InvitationStatus.PENDING,
                    Invitation.expires_at > utcnow(),
                )
                .order_by(col(Invitation.created_at).desc())
            ).all()
        )

    def pending_for_email(self, organisation_id: int, email: str) -> Invitation | None:
        return self.session.exec(
            select(Invitation).where(
                Invitation.organisation_id == organisation_id,
                Invitation.email == email,
                Invitation.status == InvitationStatus.PENDING,
                Invitation.expires_at > utcnow(),
            )
        ).first()

    def pending_for_user_email(self, email: str) -> list[Invitation]:
        return list(
            self.session.exec(
                select(Invitation)
                .where(
                    Invitation.email == email,
                    Invitation.status == InvitationStatus.PENDING,
                    Invitation.expires_at > utcnow(),
                )
                .order_by(col(Invitation.created_at).desc())
            ).all()
        )


class AuditRepository(BaseRepository):
    def log(
        self,
        organisation_id: int,
        actor_id: int | None,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        detail: str | None = None,
    ) -> None:
        self.add(
            AuditLog(
                organisation_id=organisation_id,
                actor_id=actor_id,
                action=action,
                target_type=target_type,
                target_id=target_id,
                detail=detail[:500] if detail else None,
            )
        )

    def recent(self, organisation_id: int, limit: int = 100) -> list[tuple[AuditLog, User | None]]:
        rows = self.session.exec(
            select(AuditLog, User)
            .join(User, col(User.id) == col(AuditLog.actor_id), isouter=True)
            .where(AuditLog.organisation_id == organisation_id)
            .order_by(col(AuditLog.created_at).desc(), col(AuditLog.id).desc())
            .limit(limit)
        ).all()
        return list(rows)
