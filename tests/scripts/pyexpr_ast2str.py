
################################################################################
##                                                                            ##
##  This file is part of MCPL (see https://mctools.github.io/mcpl/)           ##
##                                                                            ##
##  Copyright 2015-2026 MCPL developers.                                      ##
##                                                                            ##
##  Licensed under the Apache License, Version 2.0 (the "License");           ##
##  you may not use this file except in compliance with the License.          ##
##  You may obtain a copy of the License at                                   ##
##                                                                            ##
##      http://www.apache.org/licenses/LICENSE-2.0                            ##
##                                                                            ##
##  Unless required by applicable law or agreed to in writing, software       ##
##  distributed under the License is distributed on an "AS IS" BASIS,         ##
##  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  ##
##  See the License for the specific language governing permissions and       ##
##  limitations under the License.                                            ##
##                                                                            ##
################################################################################

# NEEDS: numpy

# Tests of the writer of expressions alone (_expr_ast2str), with trees built
# by hand: the texts of all kinds of nodes, the parentheses (only where they
# are needed), implied multiplications by units, numbers (also hexadecimal),
# statements, and that the parser reads the texts back as the same trees.

from mcpldev._expr_ast import (
    Assign,
    Binary,
    Call,
    Compare,
    Edit,
    Float,
    In,
    Int,
    Logical,
    Name,
    Part,
    Particle,
    Quantity,
    Unary,
    Unit,
    Userdata,
    Value,
    Vector,
)
from mcpldev._expr_ast2str import _expr_ast2str
from mcpldev._expr_str2ast import _expr_str2ast

a, b, c, x = Name('a'), Name('b'), Name('c'), Name('x')
one, two = Int(1), Int(2)
cm, MeV = Unit('cm'), Unit('MeV')

def check( tree, expected, kind = 'value' ):
    """The text of the tree must be the expected one, and be parsed as the
    same tree"""
    text = _expr_ast2str(tree)
    print(f'  {text!r}')
    assert text == expected, ( tree, text, expected )
    root = tree if isinstance(tree,(Value,Edit)) else Value(tree)
    assert _expr_str2ast(text,kind) == root, ( text, _expr_str2ast(text,kind), root )

def test_values():
    print('Values:')
    for tree, text in (
            ( Int(7), '7' ), ( Int(0), '0' ), ( Int(31,hex = True), '0x1f' ),
            ( Int(0,hex = True), '0x0' ), ( Float(0.5), '0.5' ), ( Float(2.0), '2.0' ),
            ( Float(1e-9), '1e-09' ), ( Float(1e30), '1e+30' ), ( Float(12345678.9), '12345678.9' ),
            ( Quantity(Int(25),'meV'), '25meV' ), ( Quantity(Float(0.5),'m'), '0.5m' ),
            ( Quantity(Int(4),'cm',2), '4cm^2' ), ( Quantity(Int(2),'cm',-1), '2cm^-1' ),
            ( Quantity(Int(2),'cm',0.5), '2cm^0.5' ), ( Quantity(Float(1e-09),'cm'), '1e-09cm' ),
            ( Quantity(Int(16,hex = True),'mm'), '0x10 mm' ), ( Quantity(Float(2.0),'eV'), '2.0eV' ),
            ( cm, 'cm' ), ( Unit('cm',-0.5), 'cm^-0.5' ), ( Name('pi'), 'pi' ),
            ( Particle('neutron'), 'neutron' ), ( Userdata('temp'), 'userdata.temp' ),
            ( Userdata('d',1), 'userdata.d.at(1)' ), ( Vector(( a, b )), '(a,b)' ),
            ( Vector(( Int(0), Int(0), Quantity(Int(1),'m') )), '(0,0,1m)' ),
            ( Part(Name('pos'),0), 'pos.x' ), ( Part(Name('pos'),2), 'pos.z' ),
            ( Part(Part(Name('v'),1),2), 'v.y.z' ), ( Part(Vector(( a, b )),1), '(a,b).y' ),
            ( Call('f',()), 'f()' ), ( Call('hypot',( x, Name('y') )), 'hypot(x,y)' ) ):
        check(tree,text)

def test_operators():
    print('Operators, with parentheses only where needed:')
    for tree, text in (
            ( Binary('+',a,Binary('*',b,c)), 'a+b*c' ),
            ( Binary('*',Binary('+',a,b),c), '(a+b)*c' ),
            ( Binary('-',Binary('-',a,b),c), 'a-b-c' ),
            ( Binary('-',a,Binary('-',b,c)), 'a-(b-c)' ),
            ( Binary('/',a,Binary('*',b,c)), 'a/(b*c)' ),
            ( Binary('//',Binary('*',a,b),c), 'a*b//c' ),
            ( Binary('|',a,Binary('&',b,c)), 'a|b&c' ),
            ( Binary('&',Binary('|',a,b),c), '(a|b)&c' ),
            ( Binary('^',a,Binary('^',b,c)), 'a^b^c' ),
            ( Binary('^',Binary('^',a,b),c), '(a^b)^c' ),
            ( Binary('^',Unary('-',a),two), '(-a)^2' ),
            ( Unary('-',Binary('^',a,two)), '-a^2' ),
            ( Binary('^',a,Unary('-',b)), 'a^-b' ),
            ( Binary('^',a,Unary('-',Binary('^',b,two))), 'a^-b^2' ),
            ( Binary('^',a,Binary('*',b,c)), 'a^(b*c)' ),
            ( Unary('-',Unary('-',a)), '--a' ), ( Unary('+',a), '+a' ),
            ( Unary('-',Binary('+',a,b)), '-(a+b)' ),
            ( Binary('*',Unary('-',a),b), '-a*b' ),
            ( Unary('-',Quantity(two,'MeV')), '-2MeV' ),
            ( Binary('^',Quantity(two,'cm'),two), '(2cm)^2' ),
            ( Binary('^',two,Quantity(two,'cm')), '2^(2cm)' ),
            ( Binary('^',MeV,Float(1000.0)), '(MeV)^1000.0' ),
            ( Binary('^',Unit('cm',2),Float(0.5)), '(cm^2)^0.5' ),
            ( Compare(a,( '<', '<' ),( b, c )), 'a<b<c' ),
            ( Compare(Compare(a,( '<', ),( b, )),( '==', ),( c, )), '(a<b)==c' ),
            ( Compare(Binary('&',a,one),( '==', ),( Int(0), )), 'a&1==0' ),
            ( Logical('or',( a, Logical('and',( b, c )) )), 'a or b and c' ),
            ( Logical('and',( Logical('or',( a, b )), c )), '(a or b) and c' ),
            ( Logical('or',( Logical('or',( a, b )), c )), '(a or b) or c' ),
            ( Logical('or',( a, b, c )), 'a or b or c' ),
            ( Unary('not',Logical('and',( a, b ))), 'not (a and b)' ),
            ( Logical('and',( Unary('not',a), b )), 'not a and b' ),
            ( Unary('not',Compare(a,( '==', ),( b, ))), 'not a==b' ),
            ( In(Name('pdgcode'),False,( Particle('neutron'), Particle('gamma') )),
              'pdgcode in (neutron,gamma)' ),
            ( In(Binary('+',a,one),True,( two, )), 'a+1 not in (2)' ),
            ( In(a,False,( Int(-11), Int(-16,hex = True), Int(0), Particle('positron') )),
              'a in (-11,-0x10,0,positron)' ),
            ( Unary('not',In(a,False,( one, two ))), 'not a in (1,2)' ),
            ( Logical('and',( In(a,False,( one, )), b )), 'a in (1) and b' ),
            ( Compare(In(a,False,( one, )),( '==', ),( b, )), '(a in (1))==b' ) ):
        check(tree,text)

def test_units():
    print('Multiplications by units (implied after a closing parenthesis):')
    for tree, text in (
            ( Binary('*',two,MeV), '2*MeV' ),
            ( Binary('*',Binary('^',two,Int(3)),MeV), '2^3MeV' ),
            ( Binary('*',Binary('+',a,b),cm), '(a+b)cm' ),
            ( Binary('*',Binary('^',two,Binary('/',Name('ekin'),MeV)),MeV), '2^(ekin/MeV)MeV' ),
            ( Binary('*',Unary('-',two),MeV), '(-2)MeV' ),
            ( Binary('*',Name('ekin'),MeV), 'ekin*MeV' ),
            ( Binary('*',Quantity(two,'cm',-1),cm), '2cm^-1*cm' ),
            ( Binary('*',cm,cm), 'cm*cm' ),
            ( Binary('*',Binary('*',a,cm),cm), 'a*cm*cm' ),
            ( Binary('/',Name('ekin'),Quantity(two,'MeV')), 'ekin/2MeV' ),
            ( Binary('/',Name('ekin'),Binary('*',two,MeV)), 'ekin/(2*MeV)' ),
            ( Binary('*',Call('sqrt',( two, )),cm), 'sqrt(2)cm' ),
            ( Binary('*',Part(Name('pos'),2),cm), 'pos.z*cm' ) ):
        check(tree,text)

def test_statements():
    print('Statements and edit expressions:')
    for tree, text, kind in (
            ( Edit(( Assign('x',None,Quantity(one,'cm')), )), 'x=1cm', 'edit' ),
            ( Edit(( Assign('x','+',two), Assign('w','^',two), Assign('n','//',two),
                     Assign('f','|',Int(4,hex = True)) )), 'x+=2;w^=2;n//=2;f|=0x4', 'edit' ),
            ( Edit(( Call('swap',( x, Name('y') )), Call('rotate_z',( Quantity(Int(90),'deg'), )) )),
              'swap(x,y);rotate_z(90deg)', 'edit' ),
            ( Edit(( Compare(x,( '>', ),( Int(0), )), )), 'x>0', 'edit' ),
            ( Edit(( Assign('r',None,Call('hypot',( x, Name('y') ))),
                     Compare(Name('r'),( '>', ),( Quantity(two,'cm'), )) )), 'r=hypot(x,y);r>2cm', 'edit' ) ):
        check(tree,text,kind)
    try:
        _expr_ast2str(Value('not a node'))
    except TypeError as e:
        print(f'Not a node: TypeError: {e}')

if __name__ == '__main__':
    test_values()
    test_operators()
    test_units()
    test_statements()
