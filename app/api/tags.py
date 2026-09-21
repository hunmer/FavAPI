"""标签管理 API：删除标签、分组增改、内容手动打标。"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import tag_store

router = APIRouter(prefix="/api/v1", tags=["tags"])


class GroupCreate(BaseModel):
    name: str
    tags: list[str] = Field(default_factory=list)


class GroupsBatch(BaseModel):
    groups: list[GroupCreate] = Field(min_length=1)


class GroupRename(BaseModel):
    name: str


class ContentTagsUpdate(BaseModel):
    tags: list[str]


class TagRename(BaseModel):
    name: str


@router.delete("/tags/{tag}")
async def delete_tag(tag: str, delete_favorites: bool = False):
    """删除标签：从所有内容的 tags 中移除；可选一并删除相关收藏关系（favorites 行）。"""
    try:
        result = await tag_store.delete_tag(tag, delete_favorites)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.put("/tags/{tag}")
async def rename_tag(tag: str, body: TagRename):
    """重命名标签：同步更新所有内容 tags 与分组定义（不动打标时间）。"""
    try:
        return await tag_store.rename_tag(tag, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/tags/{tag}/usage")
async def tag_usage(tag: str):
    return {"tag": tag, "count": await tag_store.tag_usage(tag)}


@router.post("/tag-groups", status_code=201)
async def create_group(body: GroupCreate):
    try:
        return await tag_store.create_group(body.name, body.tags)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/tag-groups/batch")
async def batch_upsert_groups(body: GroupsBatch):
    """批量合并分组（智能创建标签的一键应用）：不存在则创建，已存在则标签追加去重。"""
    return await tag_store.upsert_groups([g.model_dump() for g in body.groups])


@router.put("/tag-groups/{name}")
async def rename_group(name: str, body: GroupRename):
    try:
        return await tag_store.rename_group(name, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/contents/{content_id}/tags")
async def set_content_tags(content_id: str, body: ContentTagsUpdate):
    """手动打标：整体覆盖该内容的标签（去重、去 #、上限 10 个）。"""
    try:
        return await tag_store.set_content_tags(content_id, body.tags)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
