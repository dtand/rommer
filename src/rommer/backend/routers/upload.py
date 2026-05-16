"""Upload endpoint - handles ZIP file upload and project initialization."""

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile

from rommer.config import Project

router = APIRouter()


@router.post("/init-project")
async def init_project(
    name: str = Form(...),
    platform: str = Form(default="gba"),
    file: UploadFile = File(...),
):
    """Upload a ZIP and create a new project with agent-driven classification."""
    if Project(name).exists():
        return {"error": f"Project '{name}' already exists"}

    # Save uploaded file to temp location
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Run the same logic as CLI init-project
        from rommer.cli.commands.init_project import _extract_and_classify

        project = Project.scaffold(name, platform)

        # Create a mock args object for the handler
        class Args:
            pass
        args = Args()
        args.name = name
        args.platform = platform

        _extract_and_classify(project, Path(tmp_path), args)

        return {
            "name": name,
            "classification": [],
            "notes": "Project created successfully",
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)
