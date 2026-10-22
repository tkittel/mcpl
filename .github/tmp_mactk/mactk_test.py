#Temporary test on macOS: the open-file dialog with several filters, and
#screenshots of the viewer (native aqua theme, and with the clam theme).
import base64, pathlib, subprocess, sys, time

def screenshot(name):
    png = pathlib.Path(f'{name}.png')
    subprocess.run(['screencapture','-x',str(png)],check=False)
    if not png.exists():
        print(f'SHOT {name}: none'); return
    subprocess.run(['sips','-Z','1400',str(png)],capture_output=True)
    print(f'SHOT-BEGIN {name}')
    data = base64.b64encode(png.read_bytes()).decode()
    for i in range(0,len(data),1000):
        print(data[i:i+1000])
    print(f'SHOT-END {name}', flush=True)

dialog = '''
import sys, tkinter as tk
from tkinter import filedialog
root = tk.Tk()
print("tk", tk.TkVersion, root.tk.call("tk","windowingsystem"), flush=True)
ft = eval(sys.argv[1])
kw = {} if ft is None else {"filetypes": ft}
try:
    print("returned", repr(filedialog.askopenfilename(parent=root, title="Open an MCPL file", **kw)), flush=True)
except Exception as e:
    print("EXCEPTION", type(e).__name__, e, flush=True)
'''
variants = {
    'current' : "[('MCPL files','*.mcpl *.mcpl.gz'),('All files','*')]",
    'mcpl_gz' : "[('MCPL files','*.mcpl *.gz'),('All files','*')]",
    'exts'    : "[('MCPL files',('.mcpl','.mcpl.gz')),('All files','*')]",
    'none'    : "None",
}
for name, ft in variants.items():
    p = subprocess.Popen([sys.executable,'-c',dialog,ft],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    time.sleep(6)
    screenshot(f'dialog_{name}')
    if p.poll() is None:
        p.kill()
        print(f'DIALOG {name}: still open after 6 s (shown)')
    print(f'DIALOG {name} output:', p.communicate()[0].strip())

subprocess.run([sys.executable,'-m','mcpl','--create-examples'],check=True)
viewer = '''
import sys, mcpl._viewer_tk as vt
from mcpl._cli import main
if sys.argv[1] == 'clam':
    orig = vt._root
    def _root():
        root = orig()
        import tkinter.ttk as ttk
        ttk.Style(root).theme_use('clam')
        return root
    vt._root = _root
sys.argv = ['mcpltool','-w','mcplexample_target.mcpl.gz']
main()
'''
menu = '''
import mcpl._viewer_tk as vt
from mcpl._cli import main
import sys
orig = vt.TkViewer.start
def start(self):
    orig(self)
    #(as when "Open MCPL file..." is chosen in the menu):
    self.root.after(12000,self._ask_open)
vt.TkViewer.start = start
sys.argv = ['mcpltool','-w','mcplexample_target.mcpl.gz']
main()
'''
p = subprocess.Popen([sys.executable,'-c',menu],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
time.sleep(22)
screenshot('viewer_menu_open')
p.kill()
print('VIEWER menu_open output:', p.communicate()[0].strip()[-3000:])

for theme in ( 'aqua', 'clam' ):
    p = subprocess.Popen([sys.executable,'-c',viewer,theme],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    time.sleep(25)
    screenshot(f'viewer_{theme}')
    p.kill()
    print(f'VIEWER {theme} output:', p.communicate()[0].strip()[-2000:])
