from fastapi import APIRouter
from data.db import fetch_cluster_snapshot

router = APIRouter()


@router.get("/cluster/latest")
def get_cluster_latest():
    snapshot = fetch_cluster_snapshot()

    return {
        "status": "ok",
        "data": snapshot,
    }