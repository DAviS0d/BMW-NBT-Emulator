precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying mediump vec2 varCoordOrange;
varying mediump vec2 varCoordOrangePress;
varying mediump vec2 varCoordColor;
varying lowp vec4 preMultiplyOparam;
varying vec3 ReflectDir;
uniform float time;
uniform float param0;
uniform float param1;
uniform float param2;
uniform float param3;
uniform float oparam0;
uniform float oparam1;
uniform float oparam2;
uniform float oparam3;
varying lowp    vec3  LightVec;

varying vec3 EyespaceNormal;
varying vec3 LightPosition;

/* 
UVINFO
x = 1-0 clockwise
y = radial 1inner 0outer
*/

void main()
{
	lowp vec4 color         = texture2D( tex0, varCoordColor );
	lowp vec4 reflection    = texture2D( tex1, ReflectDir.xy );
	lowp vec4 orange        = texture2D( tex2, varCoordOrange );
	lowp vec4 orange_press  = texture2D( tex3, varCoordOrangePress );
    
	//for further design adjustments please mix colors
    gl_FragColor =  vec4( 			   color.rgb        * preMultiplyOparam.x
    								 + orange.rgb       * orange.a  * preMultiplyOparam.y
    								 + orange_press.rgb * preMultiplyOparam.z  
    							     + reflection.rgb * preMultiplyOparam.w
    									,color.a * oparam0
    							    );
    //gl_FragColor = vec4(varCoordColor.x, varCoordColor.x-fract(varCoordColor.x), 0., 1. );
}