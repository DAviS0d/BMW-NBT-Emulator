precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec2 varCoord;
varying mediump float selected_rings;
varying mediump float history_on;
varying mediump float vc;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

/*
oparam0 ... alpha
oparam1 ... ring 01 (inner) 0.0=off 1.0=active 2.0=history
oparam2 ... ring 02
oparam3 ... ring 03
oparam4 ... ring 04
oparam5 ... ring 05
oparam6 ... ring 06
oparam7 ... ring 07 (outer)
*/



void main()
{
	vec4 _active = texture2D(tex0, vec2(vc,vc));
	vec4 _history = texture2D(tex1, vec2(vc,vc)); 
	
	gl_FragColor = mix(_active, _history, history_on);
	gl_FragColor.a *= oparam0 * selected_rings;
}

