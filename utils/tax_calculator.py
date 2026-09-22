def calculate_tax(income, regime="NEW REGIME"):
    """
    Calculate tax based on regime
    """
    if regime == "NEW REGIME":
        std_deduction = 75000
        taxable = max(0, income - std_deduction)

        if taxable <= 400000:
            tax = 0
        elif taxable <= 800000:
            tax = (taxable - 400000) * 0.05
        elif taxable <= 1200000:
            tax = 20000 + (taxable - 800000) * 0.10
        else:
            tax = 60000 + (taxable - 1200000) * 0.15

        # Rebate 87A
        if taxable <= 1200000:
            tax = max(0, tax - 60000)

        # Cess 4%
        cess = tax * 0.04
        total_tax = tax + cess

        return {
            'taxable_income': taxable,
            'tax': tax,
            'cess': cess,
            'total_tax': total_tax
        }
    else:
        # Old regime calculation
        std_deduction = 50000
        taxable = max(0, income - std_deduction)

        if taxable <= 250000:
            tax = 0
        elif taxable <= 500000:
            tax = (taxable - 250000) * 0.05
        elif taxable <= 1000000:
            tax = 12500 + (taxable - 500000) * 0.20
        else:
            tax = 112500 + (taxable - 1000000) * 0.30

        cess = tax * 0.04
        total_tax = tax + cess

        return {
            'taxable_income': taxable,
            'tax': tax,
            'cess': cess,
            'total_tax': total_tax
        }
