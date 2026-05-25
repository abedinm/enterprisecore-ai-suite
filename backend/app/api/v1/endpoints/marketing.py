"""Marketing Site Builder — admin/editor endpoints.

Every route here is plan-gated by ``require_plan_feature("marketing")`` and
authenticated by ``get_current_user``. The public rendered site lives in
a separate module (``marketing_site.py``) which is mounted outside ``/api/v1``.

Owner isolation note: the marketing site is per-install (single tenant per
EnterpriseCore deployment), so any authenticated user with the marketing
feature can edit it — matching the install's "everyone in the company shares
one Studio" model.
"""
from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_plan_feature, require_roles
from app.core.exceptions import NotFoundError, ValidationFailed
from app.core.rate_limit import RateLimit
from app.db.session import get_db
from app.models.marketing import (
    MarketingFAQ, MarketingNavItem, MarketingPost, MarketingProject,
    MarketingSection, MarketingService, MarketingSocialLink,
    MarketingTeamMember, MarketingTestimonial, MarketingUpload,
)
from app.models.user import Notification, User, UserRole
from app.schemas.marketing import (
    FAQCreate, FAQOut, FAQUpdate, LaunchChecklistItem,
    MarketingSettingsOut, MarketingSettingsUpdate, MarketingStateOut,
    MarketingUploadOut, NavItemIn, NavItemOut, PostCreate, PostOut, PostUpdate,
    ProjectCreate, ProjectOut, ProjectUpdate, ReorderEntry, SectionCreate,
    SectionOut, SectionUpdate, ServiceCreate, ServiceOut, ServiceUpdate,
    SocialLinkCreate, SocialLinkOut, SocialLinkUpdate, TeamMemberCreate,
    TeamMemberOut, TeamMemberUpdate, TestimonialCreate, TestimonialOut,
    TestimonialUpdate,
)
from app.services import marketing as svc

router = APIRouter(
    dependencies=[
        Depends(require_plan_feature("marketing")),
        Depends(get_current_user),
    ]
)


# ---------------------------------------------------------------------------
# State + settings (singleton)
# ---------------------------------------------------------------------------
@router.get("/state", response_model=MarketingStateOut)
def get_state(db: Session = Depends(get_db)):
    """One payload of every marketing entity — used by the Studio editor on
    mount and by external integrations that want a full snapshot."""
    return svc.get_full_state(db)


@router.get("/settings", response_model=MarketingSettingsOut)
def get_settings(db: Session = Depends(get_db)):
    return svc.get_settings(db)


@router.patch("/settings", response_model=MarketingSettingsOut)
def update_settings(
    payload: MarketingSettingsUpdate,
    db: Session = Depends(get_db),
):
    s = svc.get_settings(db)
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is not None:
            setattr(s, key, value)
    db.commit()
    db.refresh(s)
    return s


# ---------------------------------------------------------------------------
# Navigation — bulk replace
# ---------------------------------------------------------------------------
@router.get("/navigation", response_model=list[NavItemOut])
def list_navigation(db: Session = Depends(get_db)):
    return db.scalars(
        select(MarketingNavItem).order_by(MarketingNavItem.order, MarketingNavItem.created_at)
    ).all()


@router.put("/navigation", response_model=list[NavItemOut])
def replace_navigation(
    items: list[NavItemIn],
    db: Session = Depends(get_db),
):
    """Atomically wipe + reinsert the nav list.

    Whole-list-replace is the right shape here because nav is small (5-8 items)
    and the editor always works on the full set; per-item CRUD with reorder
    would mean three round trips for what should be one atomic save."""
    db.query(MarketingNavItem).delete()
    db.flush()
    for idx, item in enumerate(items):
        db.add(
            MarketingNavItem(
                label=item.label.strip(),
                route=item.route,
                enabled=item.enabled,
                order=item.order if item.order is not None else idx,
            )
        )
    db.commit()
    return db.scalars(
        select(MarketingNavItem).order_by(MarketingNavItem.order, MarketingNavItem.created_at)
    ).all()


# ---------------------------------------------------------------------------
# Generic CRUD helpers — keeps each per-entity endpoint a couple of lines
# ---------------------------------------------------------------------------
def _get_or_404(db: Session, model_cls, obj_id: str, label: str):
    obj = db.get(model_cls, obj_id)
    if obj is None:
        raise NotFoundError(f"{label} not found")
    return obj


def _apply_update(obj, data: dict) -> None:
    for key, value in data.items():
        if value is not None:
            setattr(obj, key, value)


def _reorder(db: Session, model_cls, entries: list[ReorderEntry]) -> None:
    """Apply ``[{id, order}]`` updates. Unknown ids are silently skipped so a
    race against a concurrent delete doesn't blow up the whole save."""
    for entry in entries:
        obj = db.get(model_cls, entry.id)
        if obj is not None:
            obj.order = entry.order
    db.commit()


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------
@router.get("/sections", response_model=list[SectionOut])
def list_sections(db: Session = Depends(get_db)):
    return db.scalars(
        select(MarketingSection).order_by(MarketingSection.order, MarketingSection.created_at)
    ).all()


@router.post("/sections", response_model=SectionOut, status_code=status.HTTP_201_CREATED)
def create_section(payload: SectionCreate, db: Session = Depends(get_db)):
    obj = MarketingSection(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/sections/{obj_id}", response_model=SectionOut)
def update_section(obj_id: str, payload: SectionUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingSection, obj_id, "Section")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/sections/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_section(obj_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingSection, obj_id, "Section")
    db.delete(obj)
    db.commit()


@router.put("/sections/reorder", response_model=list[SectionOut])
def reorder_sections(entries: list[ReorderEntry], db: Session = Depends(get_db)):
    _reorder(db, MarketingSection, entries)
    return db.scalars(
        select(MarketingSection).order_by(MarketingSection.order, MarketingSection.created_at)
    ).all()


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)):
    return db.scalars(
        select(MarketingProject).order_by(MarketingProject.order, MarketingProject.created_at)
    ).all()


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    base_slug = svc.slugify(payload.title)
    slug = svc.unique_slug(db, MarketingProject, base_slug)
    obj = MarketingProject(slug=slug, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/projects/{obj_id}", response_model=ProjectOut)
def update_project(obj_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingProject, obj_id, "Project")
    data = payload.model_dump(exclude_unset=True)
    if "title" in data and data["title"] and data["title"] != obj.title:
        obj.slug = svc.unique_slug(
            db, MarketingProject, svc.slugify(data["title"]), exclude_id=obj.id
        )
    _apply_update(obj, data)
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/projects/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(obj_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingProject, obj_id, "Project")
    db.delete(obj)
    db.commit()


@router.put("/projects/reorder", response_model=list[ProjectOut])
def reorder_projects(entries: list[ReorderEntry], db: Session = Depends(get_db)):
    _reorder(db, MarketingProject, entries)
    return db.scalars(
        select(MarketingProject).order_by(MarketingProject.order, MarketingProject.created_at)
    ).all()


# ---------------------------------------------------------------------------
# Posts
# ---------------------------------------------------------------------------
@router.get("/posts", response_model=list[PostOut])
def list_posts(db: Session = Depends(get_db)):
    return db.scalars(
        select(MarketingPost).order_by(
            MarketingPost.publish_date.desc().nullslast(),
            MarketingPost.created_at.desc(),
        )
    ).all()


@router.post("/posts", response_model=PostOut, status_code=status.HTTP_201_CREATED)
def create_post(payload: PostCreate, db: Session = Depends(get_db)):
    base_slug = svc.slugify(payload.title)
    slug = svc.unique_slug(db, MarketingPost, base_slug)
    obj = MarketingPost(slug=slug, **payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/posts/{obj_id}", response_model=PostOut)
def update_post(obj_id: str, payload: PostUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingPost, obj_id, "Post")
    previous_status = obj.status
    data = payload.model_dump(exclude_unset=True)
    if "title" in data and data["title"] and data["title"] != obj.title:
        obj.slug = svc.unique_slug(
            db, MarketingPost, svc.slugify(data["title"]), exclude_id=obj.id
        )
    _apply_update(obj, data)
    db.commit()
    db.refresh(obj)
    if obj.status == "published" and previous_status != "published":
        from app.services.event_bus import publish_event

        publish_event(
            "marketing.post.published",
            payload={"post_id": obj.id, "slug": obj.slug, "title": obj.title},
        )
    return obj


@router.delete("/posts/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(obj_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingPost, obj_id, "Post")
    db.delete(obj)
    db.commit()


@router.put("/posts/reorder", response_model=list[PostOut])
def reorder_posts(entries: list[ReorderEntry], db: Session = Depends(get_db)):
    # Posts don't have an order column — they sort by publish_date — so reorder
    # is a no-op here but the endpoint exists for shape consistency.
    return db.scalars(
        select(MarketingPost).order_by(
            MarketingPost.publish_date.desc().nullslast(),
            MarketingPost.created_at.desc(),
        )
    ).all()


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------
@router.get("/services", response_model=list[ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return db.scalars(
        select(MarketingService).order_by(MarketingService.order, MarketingService.created_at)
    ).all()


@router.post("/services", response_model=ServiceOut, status_code=status.HTTP_201_CREATED)
def create_service(payload: ServiceCreate, db: Session = Depends(get_db)):
    obj = MarketingService(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/services/{obj_id}", response_model=ServiceOut)
def update_service(obj_id: str, payload: ServiceUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingService, obj_id, "Service")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/services/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_service(obj_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingService, obj_id, "Service")
    db.delete(obj)
    db.commit()


@router.put("/services/reorder", response_model=list[ServiceOut])
def reorder_services(entries: list[ReorderEntry], db: Session = Depends(get_db)):
    _reorder(db, MarketingService, entries)
    return db.scalars(
        select(MarketingService).order_by(MarketingService.order, MarketingService.created_at)
    ).all()


# ---------------------------------------------------------------------------
# Testimonials
# ---------------------------------------------------------------------------
@router.get("/testimonials", response_model=list[TestimonialOut])
def list_testimonials(db: Session = Depends(get_db)):
    return db.scalars(
        select(MarketingTestimonial).order_by(
            MarketingTestimonial.order, MarketingTestimonial.created_at
        )
    ).all()


@router.post("/testimonials", response_model=TestimonialOut, status_code=status.HTTP_201_CREATED)
def create_testimonial(payload: TestimonialCreate, db: Session = Depends(get_db)):
    obj = MarketingTestimonial(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/testimonials/{obj_id}", response_model=TestimonialOut)
def update_testimonial(obj_id: str, payload: TestimonialUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingTestimonial, obj_id, "Testimonial")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/testimonials/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_testimonial(obj_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingTestimonial, obj_id, "Testimonial")
    db.delete(obj)
    db.commit()


@router.put("/testimonials/reorder", response_model=list[TestimonialOut])
def reorder_testimonials(entries: list[ReorderEntry], db: Session = Depends(get_db)):
    _reorder(db, MarketingTestimonial, entries)
    return db.scalars(
        select(MarketingTestimonial).order_by(
            MarketingTestimonial.order, MarketingTestimonial.created_at
        )
    ).all()


# ---------------------------------------------------------------------------
# FAQs
# ---------------------------------------------------------------------------
@router.get("/faqs", response_model=list[FAQOut])
def list_faqs(db: Session = Depends(get_db)):
    return db.scalars(
        select(MarketingFAQ).order_by(MarketingFAQ.order, MarketingFAQ.created_at)
    ).all()


@router.post("/faqs", response_model=FAQOut, status_code=status.HTTP_201_CREATED)
def create_faq(payload: FAQCreate, db: Session = Depends(get_db)):
    obj = MarketingFAQ(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/faqs/{obj_id}", response_model=FAQOut)
def update_faq(obj_id: str, payload: FAQUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingFAQ, obj_id, "FAQ")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/faqs/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_faq(obj_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingFAQ, obj_id, "FAQ")
    db.delete(obj)
    db.commit()


@router.put("/faqs/reorder", response_model=list[FAQOut])
def reorder_faqs(entries: list[ReorderEntry], db: Session = Depends(get_db)):
    _reorder(db, MarketingFAQ, entries)
    return db.scalars(
        select(MarketingFAQ).order_by(MarketingFAQ.order, MarketingFAQ.created_at)
    ).all()


# ---------------------------------------------------------------------------
# Team
# ---------------------------------------------------------------------------
@router.get("/team", response_model=list[TeamMemberOut])
def list_team(db: Session = Depends(get_db)):
    return db.scalars(
        select(MarketingTeamMember).order_by(
            MarketingTeamMember.order, MarketingTeamMember.created_at
        )
    ).all()


@router.post("/team", response_model=TeamMemberOut, status_code=status.HTTP_201_CREATED)
def create_team(payload: TeamMemberCreate, db: Session = Depends(get_db)):
    obj = MarketingTeamMember(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/team/{obj_id}", response_model=TeamMemberOut)
def update_team(obj_id: str, payload: TeamMemberUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingTeamMember, obj_id, "Team member")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/team/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_team(obj_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingTeamMember, obj_id, "Team member")
    db.delete(obj)
    db.commit()


@router.put("/team/reorder", response_model=list[TeamMemberOut])
def reorder_team(entries: list[ReorderEntry], db: Session = Depends(get_db)):
    _reorder(db, MarketingTeamMember, entries)
    return db.scalars(
        select(MarketingTeamMember).order_by(
            MarketingTeamMember.order, MarketingTeamMember.created_at
        )
    ).all()


# ---------------------------------------------------------------------------
# Social links
# ---------------------------------------------------------------------------
@router.get("/social-links", response_model=list[SocialLinkOut])
def list_social_links(db: Session = Depends(get_db)):
    return db.scalars(
        select(MarketingSocialLink).order_by(
            MarketingSocialLink.order, MarketingSocialLink.created_at
        )
    ).all()


@router.post("/social-links", response_model=SocialLinkOut, status_code=status.HTTP_201_CREATED)
def create_social_link(payload: SocialLinkCreate, db: Session = Depends(get_db)):
    obj = MarketingSocialLink(**payload.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.patch("/social-links/{obj_id}", response_model=SocialLinkOut)
def update_social_link(obj_id: str, payload: SocialLinkUpdate, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingSocialLink, obj_id, "Social link")
    _apply_update(obj, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(obj)
    return obj


@router.delete("/social-links/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_social_link(obj_id: str, db: Session = Depends(get_db)):
    obj = _get_or_404(db, MarketingSocialLink, obj_id, "Social link")
    db.delete(obj)
    db.commit()


@router.put("/social-links/reorder", response_model=list[SocialLinkOut])
def reorder_social_links(entries: list[ReorderEntry], db: Session = Depends(get_db)):
    _reorder(db, MarketingSocialLink, entries)
    return db.scalars(
        select(MarketingSocialLink).order_by(
            MarketingSocialLink.order, MarketingSocialLink.created_at
        )
    ).all()


# ---------------------------------------------------------------------------
# Uploads (media library)
# ---------------------------------------------------------------------------
# Cap uploads at 5/minute per IP to keep someone from filling disk via the
# editor — separate from the (lack of) per-user quota since one install is
# typically used by one operator.
_UPLOAD_LIMIT = RateLimit("5/minute", id="marketing-upload")


@router.post(
    "/uploads",
    response_model=MarketingUploadOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_UPLOAD_LIMIT)],
)
async def upload_image(
    file: Annotated[UploadFile, File(...)],
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Upload a PNG/JPEG/WEBP up to 2 MB. The file is re-encoded server-side
    as PNG (strips EXIF + ICC) and downscaled to max 1600px on the longest
    side so disk usage stays predictable."""
    raw = await file.read()
    upload = svc.save_upload(
        db,
        user_id=current.id,
        filename=file.filename or "image.png",
        content_type=file.content_type or "application/octet-stream",
        raw=raw,
    )
    db.commit()
    db.refresh(upload)
    return upload


@router.get("/uploads", response_model=list[MarketingUploadOut])
def list_uploads(db: Session = Depends(get_db)):
    return db.scalars(
        select(MarketingUpload).order_by(MarketingUpload.created_at.desc())
    ).all()


@router.delete("/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_marketing_upload(upload_id: str, db: Session = Depends(get_db)):
    upload = _get_or_404(db, MarketingUpload, upload_id, "Upload")
    svc.delete_upload(db, upload)
    db.commit()


# ---------------------------------------------------------------------------
# Launch checklist
# ---------------------------------------------------------------------------
@router.get("/launch-checklist", response_model=list[LaunchChecklistItem])
def launch_checklist(db: Session = Depends(get_db)):
    state = svc.get_full_state(db)
    return svc.compute_launch_checklist(state)


# ---------------------------------------------------------------------------
# Industry templates (Phase 3)
#
# The gallery lists shipped templates. Picking one writes the template's
# settings + sections + services + projects + posts + ... into the install,
# wiping any existing content by default. Admin/manager only — the action is
# destructive against the current site state, so we don't let employees fire
# it accidentally.
# ---------------------------------------------------------------------------
@router.get("/templates", response_model=list[dict])
def list_marketing_templates():
    """Gallery metadata for every shipped industry template."""
    return svc.list_templates()


@router.get("/templates/{template_id}", response_model=dict)
def get_marketing_template(template_id: str):
    """Full JSON for one template — the editor uses this to render a preview
    before the user commits to applying it."""
    tpl = svc.get_template(template_id)
    if tpl is None:
        raise NotFoundError(f"Template '{template_id}' not found")
    return tpl


@router.post(
    "/templates/{template_id}/use",
    response_model=MarketingStateOut,
    dependencies=[Depends(require_roles(UserRole.admin, UserRole.manager))],
)
def use_marketing_template(
    template_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Apply a template to the current install.

    Body is ``{"wipe_existing": bool}`` — defaults to True, meaning the
    template's content replaces whatever was there. False appends instead,
    which is useful if you want to layer a starter pack onto in-progress work.
    """
    # Validate template exists before wiping anything so we don't strand the
    # install on a 404 mid-apply.
    tpl = svc.get_template(template_id)
    if tpl is None:
        raise NotFoundError(f"Template '{template_id}' not found")

    wipe = payload.get("wipe_existing", True)
    if not isinstance(wipe, bool):
        wipe = bool(wipe)

    state = svc.apply_template(db, template_id, wipe_existing=wipe)
    from app.services.event_bus import publish_event

    publish_event(
        "marketing.template.applied",
        payload={"template_id": template_id, "wipe_existing": wipe},
        user_id=current.id,
    )

    # Drop a notification on the operator's bell so the audit trail shows who
    # applied which template and when. Best-effort: if the notify insert blows
    # up (e.g. user row vanished mid-request), the template apply still stands.
    try:
        db.add(Notification(
            user_id=current.id,
            title=f"Applied template: {tpl.get('name', template_id)}",
            body=f"Industry template '{tpl.get('name', template_id)}' has been applied to your marketing site.",
            level="info",
            link="/marketing",
        ))
        db.commit()
    except Exception:  # pragma: no cover — defensive
        db.rollback()

    return state


# ---------------------------------------------------------------------------
# SiteForge JSON export import (Phase 2)
#
# SiteForge Studio operators export their browser localStorage state to JSON
# from Settings → Data → Export. This endpoint accepts that file and reshapes
# it into the EnterpriseCore marketing tables. Admin/manager only because the
# default behavior wipes the existing site state.
# ---------------------------------------------------------------------------
SITEFORGE_IMPORT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB — matches the body-size cap


@router.post(
    "/import-siteforge",
    response_model=MarketingStateOut,
    dependencies=[Depends(require_roles(UserRole.admin, UserRole.manager))],
)
async def import_siteforge(
    file: Annotated[UploadFile, File(...)],
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """Import a SiteForge Studio JSON export into the marketing module.

    The uploaded file is parsed, validated for the expected SiteForge shape
    (``siteSettings``, ``themeSettings``, ``sections``, ``projects``), and
    fed through ``apply_siteforge_export`` which wipes existing marketing
    content and inserts the import. Returns the new full state on success.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded SiteForge export is empty.",
        )
    if len(raw) > SITEFORGE_IMPORT_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"SiteForge export is too large "
                f"({len(raw)} bytes; max {SITEFORGE_IMPORT_MAX_BYTES // 1024} KB)."
            ),
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SiteForge export is not valid JSON: {exc}",
        ) from exc

    try:
        state = svc.apply_siteforge_export(db, payload, wipe_existing=True)
    except ValidationFailed as exc:
        # Bubble validation issues (missing required keys, wrong type) up as
        # 400s so the frontend file-picker can show a helpful toast.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Notify the operator that the import landed — same pattern as templates.
    try:
        site_name = (payload.get("siteSettings") or {}).get("name") or "SiteForge import"
        db.add(Notification(
            user_id=current.id,
            title=f"Imported from SiteForge: {site_name}",
            body=(
                f"Your SiteForge Studio export was imported into the Marketing "
                f"module. Existing content was replaced."
            ),
            level="info",
            link="/marketing",
        ))
        db.commit()
    except Exception:  # pragma: no cover — defensive
        db.rollback()

    return state
