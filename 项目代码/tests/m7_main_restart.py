"""Reuse full M6 dependency restart/replay assertions, preserve M6 evidence."""
import ast,os
import m7_support as h
assert h.load('M7-main-upgrade.json')['result']=='passed'
os.environ['M0_PWSH']='pwsh'
p=h.ROOT/'tests/m6_restart.py';source=p.read_text(encoding='utf-8')
changes={'M6-restart.json':'M7-restart.json','M6-replay-after-restart.json':'M7-replay-after-restart.json','.local/m6-full-restart.log':'.local/m7-full-restart.log'}
class Replace(ast.NodeTransformer):
    def visit_Constant(self,n):
        if isinstance(n.value,str):
            for old,new in changes.items():n.value=n.value.replace(old,new)
        return n
tree=ast.fix_missing_locations(Replace().visit(ast.parse(source,str(p))))
h.save('M7-restart-adapter.json',{'source':'tests/m6_restart.py','sha256':h.sha(p),'substitutions':changes,'intent':'Original main M6 browser keys and private files deliberately replayed under final V8 artifact; exact business assertions preserved.'})
exec(compile(tree,str(p),'exec'),{'__file__':str(p),'__name__':'__main__'})
