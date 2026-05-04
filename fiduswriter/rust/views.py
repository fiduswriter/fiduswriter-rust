import base64
import json
import time
from copy import deepcopy

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from document.helpers.session_user_info import SessionUserInfo
from document.helpers import document_store
from document.helpers.token_access import get_token_access
from document.models import Document, AccessRight, FW_DOCUMENT_VERSION
from document import prosemirror


@require_POST
def check_access(request):
    """Return access rights for a user and document.

    Called by the Rust WS server when a client connects.
    The caller should authenticate the user (via session cookie or
    explicit credentials) before invoking this endpoint.
    """
    response = {}
    document_id = int(request.POST.get("document_id", 0))
    token_str = request.POST.get("token", "")
    user = request.user

    # Token-based guest access
    if token_str:
        document, rights = get_token_access(token_str)
        if document and document.id == document_id:
            response["can_access"] = True
            response["access_rights"] = rights
            response["is_owner"] = False
            response["path"] = ""
            return JsonResponse(response)

    if not user.is_authenticated:
        return JsonResponse({"can_access": False}, status=401)

    user_info = SessionUserInfo(user)
    doc_db, can_access = async_to_sync(user_info.init_access)(document_id)

    if not can_access or float(doc_db.doc_version) != FW_DOCUMENT_VERSION:
        return JsonResponse({"can_access": False}, status=403)

    response["can_access"] = True
    response["access_rights"] = user_info.access_rights
    response["is_owner"] = user_info.is_owner
    response["path"] = user_info.path
    return JsonResponse(response)


@require_POST
def init_session(request):
    """Return document data for the Rust server to hold in memory.

    Called by the Rust WS server when opening a new document session.
    """
    response = {}
    document_id = int(request.POST.get("document_id", 0))
    token_str = request.POST.get("token", "")
    user = request.user

    # Resolve document
    doc = None
    access_rights = "read"
    is_owner = False
    path = ""

    if user.is_authenticated:
        doc = (
            Document.objects.filter(id=document_id)
            .select_related("owner", "template")
            .first()
        )
        if doc:
            if doc.owner_id == user.id:
                is_owner = True
                access_rights = "write"
                path = doc.path
            else:
                ar = AccessRight.objects.filter(
                    document_id=doc.id, user=user
                ).first()
                if ar:
                    access_rights = ar.rights
                    path = ar.path
                else:
                    doc = None

    if not doc and token_str:
        doc, rights = get_token_access(token_str)
        if doc and doc.id == document_id:
            access_rights = rights
            is_owner = False
            path = ""
        else:
            doc = None

    if not doc:
        return JsonResponse({}, status=401)

    # Initialize content from template if needed (sync variant)
    if isinstance(doc.content, dict) and "type" not in doc.content:
        doc.content = deepcopy(doc.template.content)
        if "type" not in doc.content:
            doc.content["type"] = "doc"
        if "content" not in doc.content:
            doc.content["content"] = [{"type": "title"}]
        doc.save()

    response["document"] = {
        "id": doc.id,
        "title": doc.title,
        "content": doc.content,
        "version": doc.version,
        "diffs": doc.diffs,
        "comments": doc.comments,
        "bibliography": doc.bibliography,
        "e2ee": doc.e2ee,
        "e2ee_salt": (
            base64.b64encode(doc.e2ee_salt).decode("ascii")
            if doc.e2ee_salt
            else None
        ),
        "e2ee_iterations": doc.e2ee_iterations,
        "e2ee_snapshot_version": doc.e2ee_snapshot_version,
    }
    response["access_rights"] = access_rights
    response["is_owner"] = is_owner
    response["path"] = path
    return JsonResponse(response)


@require_POST
def save_doc(request):
    """Persist document changes from the Rust server."""
    response = {}
    document_id = int(request.POST.get("document_id", 0))

    doc = Document.objects.filter(id=document_id).first()
    if not doc:
        return JsonResponse({"error": "Document not found"}, status=404)

    # Apply updates from the request
    content = request.POST.get("content")
    if content:
        doc.content = json.loads(content)
    title = request.POST.get("title")
    if title is not None:
        doc.title = title
    version = request.POST.get("version")
    if version is not None:
        doc.version = int(version)
    diffs = request.POST.get("diffs")
    if diffs is not None:
        doc.diffs = json.loads(diffs)
    comments = request.POST.get("comments")
    if comments is not None:
        doc.comments = json.loads(comments)
    bibliography = request.POST.get("bibliography")
    if bibliography is not None:
        doc.bibliography = json.loads(bibliography)

    e2ee_salt_b64 = request.POST.get("e2ee_salt")
    if e2ee_salt_b64 is not None:
        doc.e2ee_salt = base64.b64decode(e2ee_salt_b64)
    e2ee_iterations = request.POST.get("e2ee_iterations")
    if e2ee_iterations is not None:
        doc.e2ee_iterations = int(e2ee_iterations)
    e2ee_snapshot_version = request.POST.get("e2ee_snapshot_version")
    if e2ee_snapshot_version is not None:
        doc.e2ee_snapshot_version = int(e2ee_snapshot_version)

    # Use the helper for saving (force=True because the Rust server
    # already decided that a save is required)
    document_store.save_document(doc, force=True)

    response["version"] = doc.version
    response["saved"] = True
    return JsonResponse(response)


@require_POST
def update_images(request):
    """Update image metadata from the Rust server."""
    response = {}
    document_id = int(request.POST.get("document_id", 0))
    image_updates = json.loads(request.POST.get("image_updates", "[]"))
    user_id = int(request.POST.get("user_id", 0))

    User = get_user_model()
    user = User.objects.filter(id=user_id).first()
    if not user:
        return JsonResponse({"error": "User not found"}, status=404)

    doc = Document.objects.filter(id=document_id).first()
    if not doc:
        return JsonResponse({"error": "Document not found"}, status=404)

    document_store.update_document_images_sync(
        document_id, image_updates, user, doc_e2ee=doc.e2ee
    )

    return JsonResponse(response)
