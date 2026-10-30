precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying vec3 ReflectDir;
varying vec2 varCoord;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

varying float vc;

/* 
UVINFO
x = 1-0 clockwise
y = 1front 0back
*/

void main(){
 vec4 alpha = texture2D(tex0,varCoord.yx );
 gl_FragColor = oparam0 * (vec4 (texture2D(tex0,varCoord.yx ).rgb + texture2D(tex1,ReflectDir.xy).rgb, alpha.a ));
 gl_FragColor *= vc;
 
}
