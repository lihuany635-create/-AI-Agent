import Lobster_Core, inspect
src = inspect.getsource(Lobster_Core.LobsterCore.process_input)
lines = src.split('\n')
for i, l in enumerate(lines[:40]):
    print(i, l)
