import uuid

import django.db.models.deletion
from django.db import migrations, models


def populate_account_uuids(apps, schema_editor):
    """Assign a UUID to every existing Account row."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute('SELECT login FROM "trades_account"')
        for (login,) in cursor.fetchall():
            cursor.execute(
                'UPDATE "trades_account" SET "new_id" = %s WHERE "login" = %s',
                [str(uuid.uuid4()), login],
            )


class Migration(migrations.Migration):
    dependencies = [
        ("trades", "0003_add_trade_status_field"),
    ]

    operations = [
        # ── Simple field additions ────────────────────────────────────────────
        migrations.AddField(
            model_name="trade",
            name="environment",
            field=models.CharField(
                choices=[("PROD", "Production"), ("TEST", "Test")],
                default="PROD",
                db_index=True,
                max_length=4,
            ),
        ),
        migrations.AddField(
            model_name="account",
            name="environment",
            field=models.CharField(
                choices=[("PROD", "Production"), ("TEST", "Test")],
                default="PROD",
                max_length=4,
            ),
        ),
        # ── Account PK swap: login (BigInt) → id (UUID) ───────────────────────
        # All database work is done via raw SQL; Django's model state is updated
        # at the end via SeparateDatabaseAndState(database_operations=[]).
        # Step 1: add a temporary UUID column to Account
        migrations.RunSQL(
            sql='ALTER TABLE "trades_account" ADD COLUMN "new_id" uuid',
            reverse_sql='ALTER TABLE "trades_account" DROP COLUMN IF EXISTS "new_id"',
        ),
        # Step 2: populate it
        migrations.RunPython(populate_account_uuids, migrations.RunPython.noop),
        # Step 3: make it non-nullable
        migrations.RunSQL(
            sql='ALTER TABLE "trades_account" ALTER COLUMN "new_id" SET NOT NULL',
            reverse_sql='ALTER TABLE "trades_account" ALTER COLUMN "new_id" DROP NOT NULL',
        ),
        # Step 4: add temporary UUID FK columns to Trade and AccountSnapshot
        migrations.RunSQL(
            sql=[
                'ALTER TABLE "trades_trade" ADD COLUMN "account_id_new" uuid',
                'ALTER TABLE "trades_accountsnapshot" ADD COLUMN "account_id_new" uuid',
            ],
            reverse_sql=[
                'ALTER TABLE "trades_trade" DROP COLUMN IF EXISTS "account_id_new"',
                'ALTER TABLE "trades_accountsnapshot" DROP COLUMN IF EXISTS "account_id_new"',
            ],
        ),
        # Step 5: populate new FK columns
        migrations.RunSQL(
            sql=[
                """
                UPDATE "trades_trade" t
                SET    "account_id_new" = a."new_id"
                FROM   "trades_account" a
                WHERE  t."account_id" = a."login"
                  AND  t."account_id" IS NOT NULL
                """,
                """
                UPDATE "trades_accountsnapshot" s
                SET    "account_id_new" = a."new_id"
                FROM   "trades_account" a
                WHERE  s."account_id" = a."login"
                """,
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Step 6: drop FK constraints that reference trades_account.login
        migrations.RunSQL(
            sql="""
                DO $$
                DECLARE r RECORD;
                BEGIN
                    FOR r IN (
                        SELECT tc.constraint_name, tc.table_name
                        FROM   information_schema.table_constraints tc
                        JOIN   information_schema.referential_constraints rc
                               ON rc.constraint_name = tc.constraint_name
                        JOIN   information_schema.key_column_usage ccu
                               ON ccu.constraint_name = rc.unique_constraint_name
                        WHERE  tc.constraint_type = 'FOREIGN KEY'
                          AND  ccu.table_name = 'trades_account'
                          AND  ccu.column_name = 'login'
                    ) LOOP
                        EXECUTE 'ALTER TABLE '
                            || quote_ident(r.table_name)
                            || ' DROP CONSTRAINT '
                            || quote_ident(r.constraint_name);
                    END LOOP;
                END $$;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Step 7: drop old account_id columns and rename the new UUID ones
        migrations.RunSQL(
            sql=[
                'ALTER TABLE "trades_trade" DROP COLUMN "account_id"',
                'ALTER TABLE "trades_trade" RENAME COLUMN "account_id_new" TO "account_id"',
                'ALTER TABLE "trades_accountsnapshot" DROP COLUMN "account_id"',
                'ALTER TABLE "trades_accountsnapshot" RENAME COLUMN "account_id_new" TO "account_id"',
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Step 8: swap Account PK (login → new_id) and rename the column
        migrations.RunSQL(
            sql=[
                'ALTER TABLE "trades_account" DROP CONSTRAINT "trades_account_pkey"',
                'ALTER TABLE "trades_account" RENAME COLUMN "new_id" TO "id"',
                'ALTER TABLE "trades_account" ADD PRIMARY KEY ("id")',
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Step 9: index on Account.login (was PK, now a plain column)
        migrations.RunSQL(
            sql='CREATE INDEX "trades_account_login_3a5fc49e" ON "trades_account" ("login")',
            reverse_sql='DROP INDEX IF EXISTS "trades_account_login_3a5fc49e"',
        ),
        # Step 10: restore FK constraints and add indexes for the UUID columns
        migrations.RunSQL(
            sql=[
                """
                ALTER TABLE "trades_trade"
                ADD CONSTRAINT "trades_trade_account_id_fk_trades_account"
                FOREIGN KEY ("account_id")
                REFERENCES "trades_account" ("id")
                ON DELETE SET NULL
                DEFERRABLE INITIALLY DEFERRED
                """,
                'CREATE INDEX "trades_trade_account_id_idx" ON "trades_trade" ("account_id")',
                """
                ALTER TABLE "trades_accountsnapshot"
                ADD CONSTRAINT "trades_accountsnapshot_account_id_fk_trades_account"
                FOREIGN KEY ("account_id")
                REFERENCES "trades_account" ("id")
                ON DELETE CASCADE
                DEFERRABLE INITIALLY DEFERRED
                """,
                'CREATE INDEX "trades_accountsnapshot_account_id_idx" ON "trades_accountsnapshot" ("account_id")',
            ],
            reverse_sql=migrations.RunSQL.noop,
        ),
        # Step 11: unique constraint on (login, environment)
        migrations.RunSQL(
            sql="""
                ALTER TABLE "trades_account"
                ADD CONSTRAINT "trades_account_login_environment_uniq"
                UNIQUE ("login", "environment")
            """,
            reverse_sql='ALTER TABLE "trades_account" DROP CONSTRAINT IF EXISTS "trades_account_login_environment_uniq"',
        ),
        # ── Sync Django's internal migration state ────────────────────────────
        # database_operations=[] means "don't touch the DB" — the SQL above
        # has already done everything.  state_operations updates the model state
        # so subsequent migrations see the correct schema.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name="account",
                    name="id",
                    field=models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                    preserve_default=False,
                ),
                migrations.AlterField(
                    model_name="account",
                    name="login",
                    field=models.BigIntegerField(db_index=True),
                ),
                migrations.AlterUniqueTogether(
                    name="account",
                    unique_together={("login", "environment")},
                ),
                migrations.AlterField(
                    model_name="trade",
                    name="account",
                    field=models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="trades",
                        to="trades.account",
                    ),
                ),
            ],
        ),
    ]
