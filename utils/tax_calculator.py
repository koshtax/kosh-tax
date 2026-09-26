def calculate_tax(user_data, active_fy="2025-2026"):
    income = float(user_data.get('gross', 0))
    std_deduction = 75000  # FY 2025-26 ke liye fixed
    taxable = max(0, income - std_deduction)
    rounded_taxable = round(taxable / 10) * 10
    
    tax = 0.0
    slabs = { 'tax_slab_5': 0, 'tax_slab_10': 0, 'tax_slab_15': 0, 'tax_slab_20': 0, 'tax_slab_25': 0, 'tax_slab_30': 0 }
    
    inc = rounded_taxable
    if inc > 400000:
        if inc <= 800000:
            slabs['tax_slab_5'] = (inc - 400000) * 0.05
        elif inc <= 1200000:
            slabs['tax_slab_5'] = 20000
            slabs['tax_slab_10'] = (inc - 800000) * 0.10
        elif inc <= 1600000:
            slabs['tax_slab_5'] = 20000
            slabs['tax_slab_10'] = 40000
            slabs['tax_slab_15'] = (inc - 1200000) * 0.15
        elif inc <= 2000000:
            slabs['tax_slab_5'] = 20000
            slabs['tax_slab_10'] = 40000
            slabs['tax_slab_15'] = 60000
            slabs['tax_slab_20'] = (inc - 1600000) * 0.20
        elif inc <= 2400000:
            slabs['tax_slab_5'] = 20000
            slabs['tax_slab_10'] = 40000
            slabs['tax_slab_15'] = 60000
            slabs['tax_slab_20'] = 80000
            slabs['tax_slab_25'] = (inc - 2000000) * 0.25
        else:
            slabs['tax_slab_5'] = 20000
            slabs['tax_slab_10'] = 40000
            slabs['tax_slab_15'] = 60000
            slabs['tax_slab_20'] = 80000
            slabs['tax_slab_25'] = 100000
            slabs['tax_slab_30'] = (inc - 2400000) * 0.30

    tax = sum(slabs.values())
    
    rebate = 0.0
    if rounded_taxable <= 1200000:
        rebate = min(tax, 60000)
        tax = max(0, tax - rebate)

    cess = tax * 0.04
    total_tax = tax + cess

    return {
        'taxable_income': rounded_taxable,
        'tax_on_total_income': tax + rebate,
        'rebate_87a': rebate,
        'tax_after_rebate': tax,
        'cess': cess,
        'total_tax': total_tax,
        'tax_regime': 'new',
        'standard_deduction': std_deduction,
        **slabs
    }
