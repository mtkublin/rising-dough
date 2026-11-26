"""Settings page view models (T-UR13, ADR-0107, ADR-0136, ADR-0139).

Pure: turns the settings service context (``services.settings_drawer``), categories and cached FX
rates into the values the new-shell templates print. No I/O, no clock. Directions come from the
service's own grouping; wording from ``view_models.direction_label``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from types import MappingProxyType
from typing import Final, Protocol
from zoneinfo import ZoneInfo

from budget_planner.domain import category_colors
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.fx import FxRate
from budget_planner.repositories.invites import Invite
from budget_planner.services.invites import EXPIRED, PENDING, invite_state
from budget_planner.services.security_settings import SessionRow
from budget_planner.services.users import (
    LAST_ADMIN_DELETE_MESSAGE,
    SELF_DELETE_MESSAGE,
    AuthUser,
)
from budget_planner.web.paths import DELETE_PATH, EDIT_PATH
from budget_planner.web.view_models import direction_label

_PRESET_HEX: Final[Mapping[str, str]] = MappingProxyType(
    {preset.name: preset.cat for preset in category_colors.PRESETS}
)
_HEX_COLOUR: Final = re.compile(r"#[0-9a-fA-F]{6}")
_GROUPS: Final[tuple[tuple[str, str, str], ...]] = (
    ("expense", "Expense", "expense_categories"),
    ("income", "Income", "income_categories"),
    ("system", "System", "system_categories"),
)


@dataclass(frozen=True, slots=True)
class CategoryRowView:
    """One category row of the settings list (handoff ``rows/category-row``)."""

    id: int
    name: str
    color_name: str
    colour_text: str
    is_system: bool


@dataclass(frozen=True, slots=True)
class CategoryGroupView:
    """A settings list section: Expense, Income or System, with its count."""

    key: str
    title: str
    caption: str
    count: int
    rows: tuple[CategoryRowView, ...]


def category_row_view(category: Category) -> CategoryRowView:
    """Row values; ``color_name`` is empty for the neutral default colour."""
    colour = category_colors.category_color(category.color)
    return CategoryRowView(
        id=category.id,
        name=category.name,
        color_name=colour.name or "",
        colour_text="custom colour" if category.color else "default colour",
        is_system=category.is_system,
    )


def _members(context: Mapping[str, object], key: str) -> list[Category]:
    value = context.get(key)
    return [c for c in value if isinstance(c, Category)] if isinstance(value, list) else []


def category_groups(context: Mapping[str, object]) -> tuple[CategoryGroupView, ...]:
    """Expense, Income and System sections (empty ones omitted); archived rows are never listed."""
    groups = tuple((key, title, _members(context, source)) for key, title, source in _GROUPS)
    return tuple(
        CategoryGroupView(
            key=key,
            title=title,
            caption=f"{title} categories",
            count=len(members),
            rows=tuple(category_row_view(c) for c in members),
        )
        for key, title, members in groups
        if members
    )


def category_color_rules(categories: Sequence[Category]) -> str:
    """Style rules for stored hues outside the presets (one per distinct hue)."""
    rules = (category_colors.category_color(c.color).rule for c in categories if c.color)
    return "".join(dict.fromkeys(rule for rule in rules if rule))


@dataclass(frozen=True, slots=True)
class SwatchView:
    """One colour swatch of the category dialog."""

    name: str
    hex: str
    checked: bool


@dataclass(frozen=True, slots=True)
class CategoryFormView:
    """Values of the new / edit category dialog."""

    title: str
    name: str
    direction_text: str
    expense_checked: bool
    income_checked: bool
    default_checked: bool
    swatches: tuple[SwatchView, ...]
    preview_color: str
    usage_text: str | None


def _picked_direction(category: Category | None, direction: str | None) -> Direction:
    if category is not None:
        return category.direction
    return Direction.INCOME if direction == Direction.INCOME.value else Direction.EXPENSE


def _picked_color(category: Category | None, color: str | None) -> str:
    if color is None and category is not None:
        return category.color or ""
    return color or ""


def category_form_view(
    category: Category | None,
    *,
    name: str | None = None,
    direction: str | None = None,
    color: str | None = None,
    usage_text: str | None = None,
) -> CategoryFormView:
    """Dialog values: the stored category first, submitted values (422 re-render) over them."""
    picked = _picked_direction(category, direction)
    picked_color = _picked_color(category, color)
    valid = _HEX_COLOUR.fullmatch(picked_color) is not None
    lowered = category_colors.nearest_form_swatch(picked_color).cat if valid else ""
    preview = category_colors.category_color(lowered if valid else None)
    stored_name = category.name if category else ""
    return CategoryFormView(
        title=f"edit category · {category.name}" if category else "new category",
        name=stored_name if name is None else name,
        direction_text=direction_label(picked),
        expense_checked=picked is Direction.EXPENSE,
        income_checked=picked is Direction.INCOME,
        default_checked=not valid,
        swatches=tuple(
            SwatchView(name=swatch, hex=_PRESET_HEX[swatch], checked=_PRESET_HEX[swatch] == lowered)
            for swatch in category_colors.FORM_SWATCH_NAMES
        ),
        preview_color=preview.name or "",
        usage_text=usage_text,
    )


@dataclass(frozen=True, slots=True)
class FxRateRow:
    """One cached rate: pair text, as-of date, the rate as cached."""

    pair: str
    as_of: date
    rate_text: str


def fx_rate_rows(rates: Sequence[FxRate]) -> tuple[FxRateRow, ...]:
    """Cached rates as stored (``EUR → PLN``, the rate exactly as cached)."""
    return tuple(
        FxRateRow(
            pair=f"{r.from_ccy} → {r.to_ccy}",
            as_of=r.date,
            rate_text=str(r.rate),  # as stored; rate formatting belongs to services/fx
        )
        for r in rates
    )


def settings_page_context(raw: Mapping[str, object]) -> dict[str, object]:
    """Template context of a settings page: the service context plus its view models."""
    context = {**raw, "nav_current": "settings"}
    categories = context.get("categories")
    if isinstance(categories, list):
        context["groups"] = category_groups(context)
        context["color_rules"] = category_color_rules(
            [c for c in categories if isinstance(c, Category)]
        )
    rates = context.get("fx_rates")
    if isinstance(rates, list):
        context["fx_rows"] = fx_rate_rows([r for r in rates if isinstance(r, FxRate)])
    return context


# --- security and users (T-UR14) ----------------------------------------------------------------

USERS_PATH: Final = "/settings/users"
ACTIVE_TEXT: Final = "● active"
ROTATION_PENDING_TEXT: Final = "◐ new password required at next sign-in"


class UserListing(Protocol):
    """What the roster rows read from a listed user (``services.users.list_live_users``)."""

    @property
    def id(self) -> int: ...
    @property
    def name(self) -> str: ...
    @property
    def email(self) -> str | None: ...
    @property
    def is_admin(self) -> bool: ...
    @property
    def must_change_password(self) -> bool: ...
    @property
    def last_seen_at(self) -> datetime | None: ...


@dataclass(frozen=True, slots=True)
class UserRowView:
    """One row of the Users page (handoff ``rows/user-row``)."""

    id: int
    email_text: str
    sub_text: str
    role_text: str
    name: str
    last_seen: str
    status_text: str
    is_me: bool
    menu_id: str
    menu_sub: str
    menu_items: tuple[Mapping[str, object], ...]


def _user_menu(user_id: int) -> tuple[Mapping[str, object], ...]:
    base = f"{USERS_PATH}/{user_id}"
    return (
        MappingProxyType({"label": "edit user", "hx_get": f"{base}{EDIT_PATH}"}),
        MappingProxyType({"label": "reset password", "hx_get": f"{base}/reset-password"}),
        MappingProxyType(
            {"label": "delete user", "hx_get": f"{base}{DELETE_PATH}", "danger": True}
        ),
    )


def _user_last_seen(user: UserListing, *, is_me: bool, tz: str) -> str:
    """``now`` on the signed-in admin's own row, ``30 OCT 21:12``, or ``—`` for never signed in."""
    if is_me:
        return "now"
    return _local(user.last_seen_at, tz, "%d %b %H:%M") if user.last_seen_at else "\u2014"


def user_row_view(user: UserListing, *, me_id: int, tz: str) -> UserRowView:
    """Row values; the admin's own row carries no menu (``is_me``), ADR-0134 section 11."""
    role = "admin" if user.is_admin else "member"
    is_me = user.id == me_id
    return UserRowView(
        id=user.id,
        email_text=user.email or user.name,
        sub_text="you" if is_me else user.name,
        role_text=role,
        name=user.name,
        last_seen=_user_last_seen(user, is_me=is_me, tz=tz),
        status_text=ROTATION_PENDING_TEXT if user.must_change_password else ACTIVE_TEXT,
        is_me=is_me,
        menu_id=f"user-menu-{user.id}",
        menu_sub=f"{user.name} · {role}",
        menu_items=_user_menu(user.id),
    )


def user_rows(users: Sequence[UserListing], *, me_id: int, tz: str) -> tuple[UserRowView, ...]:
    """Roster rows in service order."""
    return tuple(user_row_view(u, me_id=me_id, tz=tz) for u in users)


INVITES_PATH: Final = "/settings/users/invites"


@dataclass(frozen=True, slots=True)
class InviteRowView:
    """One pending or expired invite on the Users page (derived from ``rows/user-row``)."""

    id: int
    email_text: str
    role_text: str
    status_text: str
    expired: bool
    menu_id: str
    menu_sub: str
    menu_items: tuple[Mapping[str, object], ...]


def _invite_menu(invite_id: int) -> tuple[Mapping[str, object], ...]:
    base = f"{INVITES_PATH}/{invite_id}"
    return (
        MappingProxyType(
            {"label": "resend invite", "hx_post": f"{base}/resend", "hx_target": "#modal-root"}
        ),
        MappingProxyType({"label": "revoke invite", "hx_get": f"{base}/revoke", "danger": True}),
    )


def invite_row_view(invite: Invite, *, now: datetime, tz: str) -> InviteRowView:
    """Row values: ``invited, expires 02 DEC`` or ``invite expired, 02 DEC`` with the mail mark."""
    expired = invite_state(invite, now=now) == EXPIRED
    stamp = _local(invite.expires_at, tz, "%d %b")
    return InviteRowView(
        id=invite.id,
        email_text=invite.email,
        role_text="admin" if invite.is_admin else "member",
        status_text=f"\u2709 invite expired \u00b7 {stamp}"
        if expired
        else f"\u2709 invited \u00b7 expires {stamp}",
        expired=expired,
        menu_id=f"invite-menu-{invite.id}",
        menu_sub="expired invite" if expired else "pending invite",
        menu_items=_invite_menu(invite.id),
    )


def invite_rows(invites: Sequence[Invite], *, now: datetime, tz: str) -> tuple[InviteRowView, ...]:
    """Pending and expired invites only (used and revoked ones leave the list), service order."""
    open_states = (PENDING, EXPIRED)
    return tuple(
        invite_row_view(i, now=now, tz=tz)
        for i in invites
        if invite_state(i, now=now) in open_states
    )


@dataclass(frozen=True, slots=True)
class UserDialogView:
    """Values of the edit, reset and delete user dialogs."""

    id: int
    email: str
    name: str
    is_admin: bool
    label: str
    is_me: bool
    blocked_reason: str | None


def delete_blocked_reason(target: AuthUser, *, me_id: int, live_admins: int) -> str | None:
    """Why this admin cannot delete ``target`` (the service guards, shown before the POST)."""
    if target.id == me_id:
        return SELF_DELETE_MESSAGE
    if target.is_admin and live_admins <= 1:
        return LAST_ADMIN_DELETE_MESSAGE
    return None


def user_dialog_view(
    target: AuthUser,
    *,
    me_id: int,
    live_admins: int,
    name: str | None = None,
    is_admin: bool | None = None,
) -> UserDialogView:
    """Dialog values: stored user first, submitted values (422 re-render) over them."""
    return UserDialogView(
        id=target.id,
        email=target.email or "",
        name=target.name if name is None else name,
        is_admin=target.is_admin if is_admin is None else is_admin,
        label=target.name or target.email or "",
        is_me=target.id == me_id,
        blocked_reason=delete_blocked_reason(target, me_id=me_id, live_admins=live_admins),
    )


def live_admin_count(users: Sequence[UserListing]) -> int:
    """Live admins in a roster listing."""
    return sum(1 for u in users if u.is_admin)


_STAMP: Final = "%d %b %H:%M"
_DAY: Final = "%d %b"
NEVER_TEXT: Final = "never"


def _local(value: datetime, tz: str, pattern: str) -> str:
    """``value`` in the display timezone as the handoff's upper-case stamp (``12 NOV 09:14``)."""
    stamp = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return stamp.astimezone(ZoneInfo(tz)).strftime(pattern).upper()


@dataclass(frozen=True, slots=True)
class SessionRowView:
    """One active session (handoff ``rows/session-row``): printed values, the revoke handle."""

    handle: str
    device: str
    ip_text: str
    title: str
    signed_in: str
    last_seen: str
    expires: str
    is_current: bool
    button_label: str


def session_row_view(row: SessionRow, tz: str) -> SessionRowView:
    """Values of a session row; the current device reads ``now`` and has no button (handoff)."""
    session = row.session
    return SessionRowView(
        handle=session.handle,
        device=row.device_label,
        ip_text=session.ip or "—",
        title=session.user_agent or "Unknown device",
        signed_in=_local(session.created_at, tz, _STAMP),
        last_seen="now" if row.is_current else _local(session.last_seen_at, tz, _STAMP),
        expires=_local(row.absolute_expires_at, tz, _DAY),
        is_current=row.is_current,
        button_label="Sign out this device" if row.is_current else f"Sign out {row.device_label}",
    )


class PasskeyListing(Protocol):
    """What a passkey row reads from a stored credential (``services.auth.list_passkeys``)."""

    @property
    def id(self) -> int: ...
    @property
    def label(self) -> str | None: ...
    @property
    def created_at(self) -> datetime: ...
    @property
    def last_used_at(self) -> datetime | None: ...


@dataclass(frozen=True, slots=True)
class PasskeyRowView:
    """One passkey: label, added and last-used stamps."""

    id: int
    label: str
    added: str
    last_used: str


def passkey_row_view(passkey: PasskeyListing, tz: str) -> PasskeyRowView:
    """Values of a passkey row (derived from the session row)."""
    return PasskeyRowView(
        id=passkey.id,
        label=passkey.label or "Passkey",
        added=_local(passkey.created_at, tz, _STAMP),
        last_used=_local(passkey.last_used_at, tz, _STAMP) if passkey.last_used_at else NEVER_TEXT,
    )
