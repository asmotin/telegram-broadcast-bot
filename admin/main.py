import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from shared.database import SessionLocal, init_db
from shared.models import AdminUser, Broadcast, BroadcastLog, Group, GroupLabel, Label

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
SUPERADMIN_IDS: set[int] = {
    int(x.strip())
    for x in os.getenv("SUPERADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

SESSION_COOKIE = "admin_session"
SESSION_VALUE = "authenticated"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Broadcast Admin", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="/app/admin/static"), name="static")
templates = Jinja2Templates(directory="/app/admin/templates")

templates.env.filters["datetime"] = lambda v: v.strftime("%d.%m.%Y %H:%M") if v else "—"


# ── Auth ───────────────────────────────────────────────────────────────────────

def check_auth(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token != f"{SESSION_VALUE}:{SECRET_KEY}":
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return True


def is_auth(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE)
    return token == f"{SESSION_VALUE}:{SECRET_KEY}"


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            SESSION_COOKIE,
            f"{SESSION_VALUE}:{SECRET_KEY}",
            httponly=True,
            max_age=86400 * 7,
        )
        return response
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})


@app.post("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, _=Depends(check_auth)):
    with SessionLocal() as db:
        total_groups = db.query(Group).filter_by(is_active=1).count()
        total_labels = db.query(Label).count()
        total_broadcasts = db.query(Broadcast).count()
        recent = db.query(Broadcast).order_by(Broadcast.sent_at.desc()).limit(5).all()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "total_groups": total_groups,
        "total_labels": total_labels,
        "total_broadcasts": total_broadcasts,
        "recent": recent,
    })


# ── Groups ─────────────────────────────────────────────────────────────────────

@app.get("/groups", response_class=HTMLResponse)
async def groups_page(request: Request, _=Depends(check_auth)):
    with SessionLocal() as db:
        groups = db.query(Group).order_by(Group.is_active.desc(), Group.title).all()
        labels = db.query(Label).order_by(Label.name).all()
    return templates.TemplateResponse("groups.html", {
        "request": request,
        "groups": groups,
        "labels": labels,
    })


@app.post("/groups/{group_id}/labels/add")
async def add_label_to_group(group_id: int, label_id: int = Form(...), _=Depends(check_auth)):
    with SessionLocal() as db:
        exists = db.query(GroupLabel).filter_by(group_id=group_id, label_id=label_id).first()
        if not exists:
            db.add(GroupLabel(group_id=group_id, label_id=label_id))
            db.commit()
    return RedirectResponse(f"/groups#{group_id}", status_code=303)


@app.post("/groups/{group_id}/labels/{label_id}/remove")
async def remove_label_from_group(group_id: int, label_id: int, _=Depends(check_auth)):
    with SessionLocal() as db:
        row = db.query(GroupLabel).filter_by(group_id=group_id, label_id=label_id).first()
        if row:
            db.delete(row)
            db.commit()
    return RedirectResponse(f"/groups#{group_id}", status_code=303)


# ── Labels ─────────────────────────────────────────────────────────────────────

@app.get("/labels", response_class=HTMLResponse)
async def labels_page(request: Request, _=Depends(check_auth)):
    with SessionLocal() as db:
        labels = db.query(Label).order_by(Label.name).all()
    return templates.TemplateResponse("labels.html", {"request": request, "labels": labels})


@app.post("/labels/create")
async def create_label(
    name: str = Form(...),
    description: str = Form(""),
    _=Depends(check_auth),
):
    clean_name = name.strip().lower().replace(" ", "_")
    with SessionLocal() as db:
        if not db.query(Label).filter_by(name=clean_name).first():
            db.add(Label(name=clean_name, description=description.strip() or None))
            db.commit()
    return RedirectResponse("/labels", status_code=303)


@app.post("/labels/{label_id}/delete")
async def delete_label(label_id: int, _=Depends(check_auth)):
    with SessionLocal() as db:
        label = db.query(Label).get(label_id)
        if label:
            db.delete(label)
            db.commit()
    return RedirectResponse("/labels", status_code=303)


@app.post("/labels/{label_id}/edit")
async def edit_label(
    label_id: int,
    description: str = Form(""),
    _=Depends(check_auth),
):
    with SessionLocal() as db:
        label = db.query(Label).get(label_id)
        if label:
            label.description = description.strip() or None
            db.commit()
    return RedirectResponse("/labels", status_code=303)


# ── Broadcasts ─────────────────────────────────────────────────────────────────

@app.get("/broadcasts", response_class=HTMLResponse)
async def broadcasts_page(request: Request, _=Depends(check_auth)):
    with SessionLocal() as db:
        labels = db.query(Label).order_by(Label.name).all()
        history = db.query(Broadcast).order_by(Broadcast.sent_at.desc()).limit(50).all()
    return templates.TemplateResponse("broadcasts.html", {
        "request": request,
        "labels": labels,
        "history": history,
    })


@app.post("/broadcasts/send")
async def send_broadcast(
    request: Request,
    label_id: int = Form(...),
    message: str = Form(...),
    _=Depends(check_auth),
):
    import asyncio
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties

    if not BOT_TOKEN:
        return templates.TemplateResponse("broadcasts.html", {
            "request": request,
            "error": "BOT_TOKEN не настроен",
            "labels": [],
            "history": [],
        })

    with SessionLocal() as db:
        label = db.query(Label).get(label_id)
        if not label:
            return RedirectResponse("/broadcasts?error=label_not_found", status_code=303)

        groups = [g for g in label.groups if g.is_active]
        broadcast = Broadcast(
            label_id=label_id,
            message=message,
            sent_by="admin_panel",
        )
        db.add(broadcast)
        db.flush()
        broadcast_id = broadcast.id

        bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
        ok, fail = 0, 0
        try:
            for group in groups:
                try:
                    await bot.send_message(group.telegram_id, message, parse_mode="HTML")
                    db.add(BroadcastLog(broadcast_id=broadcast_id, group_id=group.id, success=1))
                    ok += 1
                except Exception as e:
                    db.add(BroadcastLog(broadcast_id=broadcast_id, group_id=group.id, success=0, error=str(e)[:255]))
                    fail += 1
                await asyncio.sleep(0.05)
        finally:
            await bot.session.close()

        broadcast.success_count = ok
        broadcast.fail_count = fail
        db.commit()

    return RedirectResponse(f"/broadcasts?ok={ok}&fail={fail}", status_code=303)


@app.get("/broadcasts/{broadcast_id}/detail", response_class=HTMLResponse)
async def broadcast_detail(broadcast_id: int, request: Request, _=Depends(check_auth)):
    with SessionLocal() as db:
        broadcast = db.query(Broadcast).get(broadcast_id)
        if not broadcast:
            raise HTTPException(404)
        logs = (
            db.query(BroadcastLog)
            .filter_by(broadcast_id=broadcast_id)
            .all()
        )
    return templates.TemplateResponse("broadcast_detail.html", {
        "request": request,
        "broadcast": broadcast,
        "logs": logs,
    })


# ── Admin users ────────────────────────────────────────────────────────────────

@app.get("/admins", response_class=HTMLResponse)
async def admins_page(request: Request, _=Depends(check_auth)):
    with SessionLocal() as db:
        admins = (
            db.query(AdminUser)
            .filter_by(is_active=1)
            .order_by(AdminUser.added_at.desc())
            .all()
        )
    return templates.TemplateResponse("admins.html", {
        "request": request,
        "admins": admins,
        "superadmin_ids": sorted(SUPERADMIN_IDS),
    })


@app.post("/admins/add")
async def add_admin(
    request: Request,
    telegram_id: int = Form(...),
    username: str = Form(""),
    full_name: str = Form(""),
    _=Depends(check_auth),
):
    if telegram_id in SUPERADMIN_IDS:
        with SessionLocal() as db:
            admins = db.query(AdminUser).filter_by(is_active=1).all()
        return templates.TemplateResponse("admins.html", {
            "request": request,
            "admins": admins,
            "superadmin_ids": sorted(SUPERADMIN_IDS),
            "error": f"{telegram_id} уже является суперадмином из конфига.",
        })

    with SessionLocal() as db:
        existing = db.query(AdminUser).filter_by(telegram_id=telegram_id).first()
        if existing:
            if existing.is_active:
                admins = db.query(AdminUser).filter_by(is_active=1).all()
                return templates.TemplateResponse("admins.html", {
                    "request": request,
                    "admins": admins,
                    "superadmin_ids": sorted(SUPERADMIN_IDS),
                    "error": f"Пользователь {telegram_id} уже является администратором.",
                })
            existing.is_active = 1
            existing.username = username.lstrip("@") or existing.username
            existing.full_name = full_name or existing.full_name
            existing.added_by_name = "admin_panel"
        else:
            db.add(AdminUser(
                telegram_id=telegram_id,
                username=username.lstrip("@") or None,
                full_name=full_name or None,
                added_by_name="admin_panel",
            ))
        db.commit()

    return RedirectResponse("/admins?success=1", status_code=303)


@app.post("/admins/{admin_id}/remove")
async def remove_admin(admin_id: int, _=Depends(check_auth)):
    with SessionLocal() as db:
        admin_user = db.query(AdminUser).get(admin_id)
        if admin_user:
            if admin_user.telegram_id in SUPERADMIN_IDS:
                # Safety: never deactivate a superadmin row if one exists in DB
                pass
            else:
                admin_user.is_active = 0
                db.commit()
    return RedirectResponse("/admins", status_code=303)
