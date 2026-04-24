from flask import Blueprint, render_template


pages_bp = Blueprint("pages", __name__)


@pages_bp.get("/")
def index():
    return render_template("index.html", page_name="library")


@pages_bp.get("/settings")
def settings():
    return render_template("settings.html", page_name="settings")


@pages_bp.get("/watch/<int:item_id>")
def watch(item_id: int):
    return render_template("watch.html", page_name="watch", item_id=item_id)
