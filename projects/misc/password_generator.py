def password_generator(length=12):
    import random
    import string

    def get_random_password(length):
        all_characters = string.ascii_letters + string.digits + string.punctuation
        password = ''.join(random.choice(all_characters) for i in range(length))
        return password

    return get_random_password(length)

# 測試功能
print(password_generator())