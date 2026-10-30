precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying vec2 varCoord;
varying vec2 varCoord2;
varying mediump vec2 varCoord3;
varying mediump vec2 varCoord4;
varying mediump vec2 varCoord5;
varying mediump vec2 varCoord6;
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
	vec4 tex_bg = texture2D(tex2, varCoord.yx );
	vec4 icon = texture2D( tex0, varCoord2 );

	// shadow
	vec4 tmp;
	tmp.x = texture2D( tex0, varCoord3 ).a;
	tmp.y = texture2D( tex0, varCoord4 ).a;
	tmp.z = texture2D( tex0, varCoord5 ).a;
	tmp.w = texture2D( tex0, varCoord6 ).a;
	vec2 tmp2 = tmp.xy + tmp.zw;
	float f = tmp2.x + tmp2.y;

	gl_FragColor.rgb = clamp( tex_bg.rgb - vec3( f ), 0.0, 1.0 ) + 1.1 * icon.rgb * icon.a;
	gl_FragColor.a = oparam0;
}