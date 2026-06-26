def display_product(qty=1, item="apple", price=0.99):
    print(f"{qty} {item} cost ${price:.2f}")

display_product()
display_product(5, "oranges", 2.50)
display_product(item="milk", price=1.20, qty=2)