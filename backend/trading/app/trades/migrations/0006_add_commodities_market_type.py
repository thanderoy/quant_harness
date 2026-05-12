from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trades", "0005_alter_account_id"),
    ]

    operations = [
        migrations.AlterField(
            model_name="trade",
            name="market_type",
            field=models.CharField(
                max_length=50,
                choices=[
                    ("FOREX", "Forex"),
                    ("CRYPTO", "Crypto"),
                    ("COMMODITIES", "Commodities"),
                    ("OTHER", "Other"),
                ],
            ),
        ),
    ]
