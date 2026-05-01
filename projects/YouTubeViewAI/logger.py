import win32com as w
try:
    self.logWindow = w.GetInterface("IDIB001")
except Exception as e:
    self.logWindow = None

self.logWindow.Visible()
self.logWindow.SetHeight(400)