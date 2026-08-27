"""拆分公司与产品资料并迁移旧备案数据。

Revision ID: 20260827_0018
Revises: 20260827_0017
"""

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "20260827_0018"
down_revision: str | None = "20260827_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_FILE_KEYS = {
    "fund_filing_file",
    "fund_contract_file",
    "custodian_account_file",
    "holder_register_file",
    "securities_accounts_file",
    "commitment_file",
    "fund_agreement_file",
}


def upgrade() -> None:
    with op.batch_alter_table("field_definition") as batch:
        batch.add_column(sa.Column("legacy_filing_field_id", sa.Integer()))
        batch.create_unique_constraint(
            "uq_field_definition_legacy_filing_field", ["legacy_filing_field_id"]
        )
    with op.batch_alter_table("source_document") as batch:
        batch.add_column(sa.Column("legacy_filing_file_version_id", sa.Integer()))
        batch.create_unique_constraint(
            "uq_source_document_legacy_filing_version", ["legacy_filing_file_version_id"]
        )
    with op.batch_alter_table("fund_product") as batch:
        batch.add_column(sa.Column("entity_id", sa.Integer()))
        batch.create_foreign_key(
            "fk_fund_product_entity_id_entity", "entity", ["entity_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_unique_constraint("uq_fund_product_entity_id", ["entity_id"])
    op.create_index("ix_fund_product_entity_id", "fund_product", ["entity_id"])

    op.create_table(
        "organization_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("legacy_filing_profile_id", sa.Integer()),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("entity_id", name="uq_organization_profile_entity_id"),
        sa.UniqueConstraint("legacy_filing_profile_id", name="uq_organization_profile_legacy"),
        sa.UniqueConstraint("tenant_id", name="uq_organization_profile_tenant_id"),
    )
    for column in ("tenant_id", "entity_id"):
        op.create_index(f"ix_organization_profile_{column}", "organization_profile", [column])

    op.create_table(
        "fund_product_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("fund_product_id", sa.Integer(), nullable=False),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["entity_id"], ["entity.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["fund_product_id"], ["fund_product.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("entity_id", name="uq_fund_product_profile_entity_id"),
        sa.UniqueConstraint("fund_product_id", name="uq_fund_product_profile_product_id"),
    )
    for column in ("tenant_id", "entity_id", "fund_product_id"):
        op.create_index(f"ix_fund_product_profile_{column}", "fund_product_profile", [column])

    op.create_table(
        "product_material_attribution",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("product_entity_id", sa.Integer()),
        sa.Column("assigned_by_user_id", sa.Integer()),
        sa.Column("assigned_at", sa.DateTime()),
        sa.Column("notes", sa.String(500)),
        sa.Column("create_time", sa.DateTime(), nullable=False),
        sa.Column("update_time", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["document_id"], ["source_document.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["product_entity_id"], ["entity.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_by_user_id"], ["app_user.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("document_id", name="uq_product_material_document"),
    )
    for column in ("tenant_id", "document_id", "product_entity_id", "assigned_by_user_id"):
        op.create_index(
            f"ix_product_material_attribution_{column}",
            "product_material_attribution",
            [column],
        )

    _migrate_existing_data(op.get_bind())


def _migrate_existing_data(connection: sa.Connection) -> None:
    metadata = sa.MetaData()
    metadata.reflect(bind=connection)
    tables = metadata.tables
    now = datetime.now(UTC).replace(tzinfo=None)
    entity = tables["entity"]
    organization_profile = tables["organization_profile"]
    product_profile = tables["fund_product_profile"]
    fund_product = tables["fund_product"]
    filing_profile = tables["filing_profile"]
    filing_field = tables["filing_field"]
    filing_version = tables["filing_file_version"]
    field_definition = tables["field_definition"]
    field_value = tables["field_value"]
    source_document = tables["source_document"]
    document_relation = tables["document_relation"]
    attribution = tables["product_material_attribution"]
    tenant = tables["tenant"]

    organization_entities: dict[int, int] = {}
    for tenant_row in connection.execute(sa.select(tenant)).mappings():
        organization_id = connection.scalar(
            sa.select(entity.c.id)
            .where(entity.c.tenant_id == tenant_row["id"], entity.c.entity_type == "organization")
            .order_by(entity.c.id)
            .limit(1)
        )
        if organization_id is None:
            result = connection.execute(
                sa.insert(entity).values(
                    tenant_id=tenant_row["id"],
                    entity_type="organization",
                    display_name=tenant_row["name"],
                    external_code=f"tenant-{tenant_row['id']}-organization",
                    status="active",
                    create_time=now,
                    update_time=now,
                )
            )
            organization_id = result.inserted_primary_key[0]
        organization_entities[tenant_row["id"]] = organization_id

        legacy_profile_id = connection.scalar(
            sa.select(filing_profile.c.id).where(filing_profile.c.tenant_id == tenant_row["id"])
        )
        if (
            connection.scalar(
                sa.select(organization_profile.c.id).where(
                    organization_profile.c.entity_id == organization_id
                )
            )
            is None
        ):
            connection.execute(
                sa.insert(organization_profile).values(
                    tenant_id=tenant_row["id"],
                    entity_id=organization_id,
                    legacy_filing_profile_id=legacy_profile_id,
                    create_time=now,
                    update_time=now,
                )
            )

    for product in connection.execute(sa.select(fund_product)).mappings():
        product_entity_id = connection.scalar(
            sa.select(entity.c.id).where(
                entity.c.tenant_id == product["tenant_id"],
                entity.c.entity_type == "product",
                entity.c.external_code == product["product_code"],
            )
        )
        if product_entity_id is None:
            result = connection.execute(
                sa.insert(entity).values(
                    tenant_id=product["tenant_id"],
                    entity_type="product",
                    display_name=product["product_name"],
                    external_code=product["product_code"],
                    status="active",
                    create_time=now,
                    update_time=now,
                )
            )
            product_entity_id = result.inserted_primary_key[0]
        connection.execute(
            sa.update(fund_product)
            .where(fund_product.c.id == product["id"])
            .values(entity_id=product_entity_id)
        )
        if (
            connection.scalar(
                sa.select(product_profile.c.id).where(
                    product_profile.c.fund_product_id == product["id"]
                )
            )
            is None
        ):
            connection.execute(
                sa.insert(product_profile).values(
                    tenant_id=product["tenant_id"],
                    entity_id=product_entity_id,
                    fund_product_id=product["id"],
                    create_time=now,
                    update_time=now,
                )
            )

    definitions: dict[int, int] = {}
    fields = list(connection.execute(sa.select(filing_field)).mappings())
    for field in fields:
        if field["field_type"] != "text":
            continue
        definition_id = connection.scalar(
            sa.select(field_definition.c.id).where(
                field_definition.c.legacy_filing_field_id == field["id"]
            )
        )
        if definition_id is None:
            definition_id = connection.scalar(
                sa.select(field_definition.c.id).where(
                    field_definition.c.tenant_id == field["tenant_id"],
                    field_definition.c.entity_type == "organization",
                    field_definition.c.field_code == field["field_key"],
                )
            )
            if definition_id is not None:
                connection.execute(
                    sa.update(field_definition)
                    .where(field_definition.c.id == definition_id)
                    .values(legacy_filing_field_id=field["id"])
                )
        if definition_id is None:
            result = connection.execute(
                sa.insert(field_definition).values(
                    tenant_id=field["tenant_id"],
                    entity_type="organization",
                    field_code=field["field_key"],
                    label=field["label"],
                    data_type="string",
                    category=field["category"],
                    sensitivity="sensitive" if field["sensitive"] else "normal",
                    is_multivalue=False,
                    validation_schema={},
                    display_schema={"multiline": bool(field["multiline"])},
                    sort_order=field["sort_order"],
                    is_system=not field["field_key"].startswith("custom_"),
                    is_active=field["is_active"],
                    legacy_filing_field_id=field["id"],
                    create_time=field["create_time"],
                    update_time=field["update_time"],
                )
            )
            definition_id = result.inserted_primary_key[0]
        definitions[field["id"]] = definition_id

    field_by_key = {(row["tenant_id"], row["field_key"]): row for row in fields}
    for profile in connection.execute(sa.select(filing_profile)).mappings():
        organization_id = organization_entities[profile["tenant_id"]]
        for field_key, value in (profile["field_values"] or {}).items():
            field = field_by_key.get((profile["tenant_id"], field_key))
            if field is None or not value:
                continue
            connection.execute(
                sa.insert(field_value).values(
                    tenant_id=profile["tenant_id"],
                    entity_id=organization_id,
                    field_definition_id=definitions[field["id"]],
                    value_json=value,
                    status="confirmed",
                    valid_from=profile["update_time"],
                    source_type="legacy_migration",
                    source_locator_json={"filing_profile_id": profile["id"]},
                    confidence=100,
                    create_time=now,
                )
            )

    fields_by_id = {row["id"]: row for row in fields}
    for version in connection.execute(sa.select(filing_version)).mappings():
        field = fields_by_id[version["field_id"]]
        is_product_material = field["field_key"] in PRODUCT_FILE_KEYS
        organization_id = organization_entities[version["tenant_id"]]
        result = connection.execute(
            sa.insert(source_document).values(
                tenant_id=version["tenant_id"],
                document_key=f"legacy-filing-field-{field['id']}",
                entity_id=None if is_product_material else organization_id,
                document_type=field["field_key"],
                original_name=version["original_name"],
                mime_type=version["content_type"] or "application/octet-stream",
                content_hash=version["content_hash"],
                storage_path=version["stored_path"],
                file_size=version["file_size"],
                version=version["version"],
                source_channel="manual_upload",
                sensitivity="sensitive" if field["sensitive"] else "normal",
                uploaded_by_user_id=version["created_by_user_id"],
                legacy_filing_file_version_id=version["id"],
                create_time=version["create_time"],
            )
        )
        document_id = result.inserted_primary_key[0]
        if is_product_material:
            connection.execute(
                sa.insert(attribution).values(
                    tenant_id=version["tenant_id"],
                    document_id=document_id,
                    status="pending",
                    create_time=now,
                    update_time=now,
                )
            )
        else:
            connection.execute(
                sa.insert(document_relation).values(
                    tenant_id=version["tenant_id"],
                    document_id=document_id,
                    entity_id=organization_id,
                    relation_type="legacy_company_material",
                    create_time=now,
                )
            )


def downgrade() -> None:
    op.drop_table("product_material_attribution")
    op.drop_table("fund_product_profile")
    op.drop_table("organization_profile")
    op.drop_index("ix_fund_product_entity_id", table_name="fund_product")
    with op.batch_alter_table("fund_product") as batch:
        batch.drop_constraint("uq_fund_product_entity_id", type_="unique")
        batch.drop_constraint("fk_fund_product_entity_id_entity", type_="foreignkey")
        batch.drop_column("entity_id")
    with op.batch_alter_table("source_document") as batch:
        batch.drop_constraint("uq_source_document_legacy_filing_version", type_="unique")
        batch.drop_column("legacy_filing_file_version_id")
    with op.batch_alter_table("field_definition") as batch:
        batch.drop_constraint("uq_field_definition_legacy_filing_field", type_="unique")
        batch.drop_column("legacy_filing_field_id")
