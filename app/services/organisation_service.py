from datetime import timedelta

from sqlmodel import Session

from app.config.settings import settings
from app.core.time import utcnow
from app.exceptions.exception import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.repositories.organisation_repository import AuditRepository, InvitationRepository, OrganisationRepository
from app.repositories.task_repository import TodoRepository
from app.repositories.team_repository import TeamRepository
from app.repositories.user_repository import UserRepository
from app.schemas.models.enums.role import OrgRole
from app.schemas.models.enums.status import InvitationStatus, MembershipStatus
from app.schemas.models.organisation import Invitation, Organisation, OrganisationMember
from app.schemas.models.user import User
from app.schemas.responses.responses import AuditLogOut, InvitationOut, OrgMemberOut
from app.services.access import AccessControl
from app.services.email_service import Mailer


class OrganisationService:
    def __init__(self, session: Session):
        self.session = session
        self.orgs = OrganisationRepository(session)
        self.users = UserRepository(session)
        self.teams = TeamRepository(session)
        self.todos = TodoRepository(session)
        self.audit = AuditRepository(session)

    # -- organisations ------------------------------------------------------
    def create(self, user: User, name: str) -> tuple[Organisation, OrganisationMember]:
        if not user.email_verified:
            raise ForbiddenError("Confirm your email address before creating an organisation.", "email_not_verified")
        organisation = self.orgs.add(Organisation(name=name, created_by_id=user.id))
        # Creating an organisation is the only way to become an owner. Nobody picks a role at sign-up.
        membership = self.orgs.add(
            OrganisationMember(organisation_id=organisation.id, user_id=user.id, role=OrgRole.OWNER)
        )
        self.audit.log(organisation.id, user.id, "organisation.created", "organisation", organisation.id, name)
        self.session.commit()
        return organisation, membership

    def mine(self, user: User) -> list[tuple[OrganisationMember, Organisation]]:
        return self.orgs.memberships_for_user(user.id)

    def rename(self, actor: OrganisationMember, name: str) -> Organisation:
        if actor.role != OrgRole.OWNER:
            raise ForbiddenError("Only an owner can rename the organisation.")
        organisation = self.orgs.get(actor.organisation_id)
        old = organisation.name
        organisation.name = name
        self.session.add(organisation)
        self.audit.log(organisation.id, actor.user_id, "organisation.renamed", "organisation", organisation.id, f"{old} → {name}")
        self.session.commit()
        return organisation

    # -- members ------------------------------------------------------------
    def members(self, actor: OrganisationMember) -> list[OrgMemberOut]:
        team_counts = self.orgs.team_counts(actor.organisation_id)
        return [
            OrgMemberOut(
                user_id=user.id,
                name=user.name,
                email=user.email,
                role=membership.role,
                joined_at=membership.joined_at,
                team_count=team_counts.get(user.id, 0),
            )
            for membership, user in self.orgs.members(actor.organisation_id)
        ]

    def change_role(self, actor: OrganisationMember, target_user_id: int, role: OrgRole) -> None:
        if actor.role != OrgRole.OWNER:
            raise ForbiddenError("Only an owner can change roles.")
        target = self._active_target(actor, target_user_id)
        if target.role == role:
            return
        if target.role == OrgRole.OWNER and self.orgs.active_owner_count(actor.organisation_id) <= 1:
            raise ConflictError(
                "An organisation needs at least one owner. Make someone else an owner first.", "last_owner"
            )
        previous = target.role
        target.role = role
        self.session.add(target)
        self.audit.log(
            actor.organisation_id,
            actor.user_id,
            "member.role_changed",
            "user",
            target_user_id,
            f"{self._label(target_user_id)}: {previous.value} → {role.value}",
        )
        self.session.commit()

    def remove_member(self, actor: OrganisationMember, target_user_id: int) -> None:
        if target_user_id == actor.user_id:
            raise BadRequestError("To remove yourself, use Leave organisation.")
        target = self._active_target(actor, target_user_id)
        if actor.role == OrgRole.ADMIN and target.role != OrgRole.MEMBER:
            raise ForbiddenError("Admins can only remove regular members.")
        if actor.role == OrgRole.MEMBER:
            raise ForbiddenError("Only owners and admins can remove members.")
        self._detach(target, MembershipStatus.REMOVED, actor.user_id, "member.removed")

    def leave(self, actor: OrganisationMember) -> None:
        if actor.role == OrgRole.OWNER and self.orgs.active_owner_count(actor.organisation_id) <= 1:
            raise ConflictError(
                "You are the only owner. Make someone else an owner before you leave.", "last_owner"
            )
        self._detach(actor, MembershipStatus.LEFT, actor.user_id, "member.left")

    def recent_activity(self, actor: OrganisationMember) -> list[AuditLogOut]:
        if not AccessControl.is_org_admin(actor):
            raise ForbiddenError("Only owners and admins can view the activity log.")
        return [
            AuditLogOut(
                id=entry.id,
                actor_name=person.name if person else None,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                detail=entry.detail,
                created_at=entry.created_at,
            )
            for entry, person in self.audit.recent(actor.organisation_id)
        ]

    # -- helpers --------------------------------------------------------------
    def _active_target(self, actor: OrganisationMember, user_id: int) -> OrganisationMember:
        target = self.orgs.active_membership(actor.organisation_id, user_id)
        if target is None:
            raise NotFoundError("That person is not a member of this organisation.")
        return target

    def _label(self, user_id: int) -> str:
        user = self.users.get(user_id)
        return f"{user.name} ({user.email})" if user else f"user {user_id}"

    def _detach(self, membership: OrganisationMember, status: MembershipStatus, actor_id: int, action: str) -> None:
        """End a membership without deleting history: leave their teams, release their open todos."""
        membership.status = status
        membership.left_at = utcnow()
        self.session.add(membership)
        teams_left = self.teams.deactivate_user_in_org(membership.organisation_id, membership.user_id)
        released = self.todos.todos_in_org_for_user(membership.organisation_id, membership.user_id)
        for todo in released:
            todo.assigned_to_id = None
            todo.updated_at = utcnow()
            self.session.add(todo)
        self.audit.log(
            membership.organisation_id,
            actor_id,
            action,
            "user",
            membership.user_id,
            f"{self._label(membership.user_id)} · left {teams_left} team(s), {len(released)} open todo(s) unassigned",
        )
        self.session.commit()


class InvitationService:
    def __init__(self, session: Session, mailer: Mailer):
        self.session = session
        self.mailer = mailer
        self.orgs = OrganisationRepository(session)
        self.invitations = InvitationRepository(session)
        self.users = UserRepository(session)
        self.audit = AuditRepository(session)

    def create(self, actor: OrganisationMember, email: str, role: OrgRole) -> InvitationOut:
        if actor.role == OrgRole.MEMBER:
            raise ForbiddenError("Only owners and admins can invite people.")
        if actor.role == OrgRole.ADMIN and role != OrgRole.MEMBER:
            raise ForbiddenError("Admins can only invite people as members. Ask an owner for a higher role.")
        existing_user = self.users.find_by_email(email)
        if existing_user and self.orgs.active_membership(actor.organisation_id, existing_user.id):
            raise ConflictError("That person is already in this organisation.", "already_member")
        if self.invitations.pending_for_email(actor.organisation_id, email):
            raise ConflictError("That email address already has a pending invitation.", "already_invited")

        invitation = self.invitations.add(
            Invitation(
                organisation_id=actor.organisation_id,
                email=email,
                role=role,
                invited_by_id=actor.user_id,
                expires_at=utcnow() + timedelta(days=settings.INVITATION_DAYS),
            )
        )
        organisation = self.orgs.get(actor.organisation_id)
        inviter = self.users.get(actor.user_id)
        self.audit.log(
            actor.organisation_id, actor.user_id, "invitation.sent", "invitation", invitation.id, f"{email} as {role.value}"
        )
        self.session.commit()
        self.mailer.send_invitation(email, inviter.name, organisation.name, role.value)
        return self._out(invitation, organisation.name, inviter.name)

    def pending_for_org(self, actor: OrganisationMember) -> list[InvitationOut]:
        if actor.role == OrgRole.MEMBER:
            raise ForbiddenError("Only owners and admins can see invitations.")
        organisation = self.orgs.get(actor.organisation_id)
        return [
            self._out(inv, organisation.name, (self.users.get(inv.invited_by_id)).name)
            for inv in self.invitations.pending_for_org(actor.organisation_id)
        ]

    def revoke(self, actor: OrganisationMember, invitation_id: int) -> None:
        if actor.role == OrgRole.MEMBER:
            raise ForbiddenError("Only owners and admins can revoke invitations.")
        invitation = self.invitations.get(invitation_id)
        if invitation is None or invitation.organisation_id != actor.organisation_id:
            raise NotFoundError("Invitation not found.")
        if invitation.status != InvitationStatus.PENDING:
            raise BadRequestError("This invitation is no longer pending.")
        invitation.status = InvitationStatus.REVOKED
        invitation.responded_at = utcnow()
        self.session.add(invitation)
        self.audit.log(
            actor.organisation_id, actor.user_id, "invitation.revoked", "invitation", invitation.id, invitation.email
        )
        self.session.commit()

    # -- the invited person's side ------------------------------------------------
    def mine(self, user: User) -> list[InvitationOut]:
        result = []
        for inv in self.invitations.pending_for_user_email(user.email):
            organisation = self.orgs.get(inv.organisation_id)
            inviter = self.users.get(inv.invited_by_id)
            result.append(self._out(inv, organisation.name, inviter.name if inviter else "Someone"))
        return result

    def accept(self, user: User, invitation_id: int) -> OrganisationMember:
        invitation = self._mine_pending(user, invitation_id)
        membership = self.orgs.any_membership(invitation.organisation_id, user.id)
        if membership is None:
            membership = self.orgs.add(
                OrganisationMember(organisation_id=invitation.organisation_id, user_id=user.id, role=invitation.role)
            )
        elif membership.status != MembershipStatus.ACTIVE:
            # Returning after leaving, or moving back to a former employer: same row, fresh start.
            membership.status = MembershipStatus.ACTIVE
            membership.role = invitation.role
            membership.joined_at = utcnow()
            membership.left_at = None
            self.session.add(membership)
        invitation.status = InvitationStatus.ACCEPTED
        invitation.responded_at = utcnow()
        self.session.add(invitation)
        self.audit.log(
            invitation.organisation_id, user.id, "member.joined", "user", user.id, f"{user.name} as {invitation.role.value}"
        )
        self.session.commit()
        return membership

    def decline(self, user: User, invitation_id: int) -> None:
        invitation = self._mine_pending(user, invitation_id)
        invitation.status = InvitationStatus.DECLINED
        invitation.responded_at = utcnow()
        self.session.add(invitation)
        self.session.commit()

    def _mine_pending(self, user: User, invitation_id: int) -> Invitation:
        invitation = self.invitations.get(invitation_id)
        # Someone else's invitation is reported as missing, not forbidden.
        if invitation is None or invitation.email != user.email:
            raise NotFoundError("Invitation not found.")
        if invitation.status != InvitationStatus.PENDING or invitation.expires_at < utcnow():
            raise BadRequestError("This invitation is no longer valid. Ask for a new one.", "invitation_expired")
        return invitation

    @staticmethod
    def _out(invitation: Invitation, organisation_name: str, inviter_name: str) -> InvitationOut:
        return InvitationOut(
            id=invitation.id,
            organisation_id=invitation.organisation_id,
            organisation_name=organisation_name,
            email=invitation.email,
            role=invitation.role,
            status=invitation.status,
            invited_by_name=inviter_name,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
        )
