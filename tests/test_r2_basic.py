from pems.storage import R2StorageHandler

try:
    handler = R2StorageHandler()
    print("should be error but no error raised")
except ValueError as e:
    print(f"Correct Error is: {e}")
