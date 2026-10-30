precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying vec2 varCoord;
varying vec2 varCoord2;
varying vec2 varCoord3;
uniform float time;
uniform float param0;
uniform float param1;
uniform float param2;
uniform float param3;
uniform float oparam0;
uniform float oparam1;
uniform float oparam2;
uniform float oparam3;
uniform float oparam4;
uniform float oparam5;
uniform float oparam6;
uniform float oparam7;

//#define vec4 mediump vec4
//#define vec3 mediump vec3
//#define vec2 mediump vec2
//#define float mediump float

#define toggle_state step(0.5, oparam2) 

/* 
oparam1: state switch   0=empty 1=inactive 2=active 3=cursored
oparam2: icon color switch 
oparam3: translate all element x
oparam4: translate icon x
oparam5: translate icon y
oparam6: scale icon x
oparam7: scale icon y
*/


void main()
{
	vec4 tex_bg = texture2D( tex1, varCoord3 );
	vec4 icon = texture2D( tex0, varCoord2 );

	gl_FragColor.rgb = tex_bg.rgb + 1.1 * icon.rgb * icon.a;
	gl_FragColor.a = oparam0;
}