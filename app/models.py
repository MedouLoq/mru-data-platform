from django.db import models

class Asset(models.Model):
    CATEGORY_CHOICES = [('currency', 'Currency'), ('commodity', 'Commodity')]
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)

    def __str__(self):
        return self.code

class Price(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE)
    date = models.DateField()
    value_mru = models.DecimalField(max_digits=20, decimal_places=4)
    source = models.CharField(max_length=100, default='BCM')
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['asset', 'date'], name='unique_price_per_day')
        ]