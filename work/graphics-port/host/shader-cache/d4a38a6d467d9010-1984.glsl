precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;

varying mediump vec2 varCoord;
varying mediump vec4 varCoord1;
varying mediump vec4 varCoord2;
varying mediump vec4 varCoord3;
varying mediump vec4 varCoord4;
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

/**************************************************************************************
oparam0 = alpha fade
oparam4 = font x translate 
oparam5 = font y translate 
oparam6 = font width 
oparam7 = font height
**********************************************************************************/

void main()
{
	// FONT SHADOW
	vec4 font = texture2D( tex0, varCoord.xy );
	
	vec4 tmpA = vec4( 	texture2D( tex0, varCoord1.xy ).a,
 						texture2D( tex0, varCoord1.zw ).a,
 						texture2D( tex0, varCoord2.xy ).a,
 						texture2D( tex0, varCoord2.zw ).a );
 						
	vec4 tmpB = vec4( 	texture2D( tex0, varCoord3.xy ).a,
 						texture2D( tex0, varCoord3.zw ).a,
 						texture2D( tex0, varCoord4.xy ).a,
 						texture2D( tex0, varCoord4.zw ).a * 1.0/9.0 );

	vec4 tmpC = tmpA + tmpB;
	vec2 tmpD = tmpC.xy + tmpC.zw;
	float shadow = ( font.a + tmpD.x + tmpD.y ) * oparam0;
	
	gl_FragColor.rgb = font.rgb;
	gl_FragColor.a = shadow;
}
