precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying vec3 ReflectDir;
varying vec2 varCoord;
uniform float time;
uniform float param0;
uniform float param1;
uniform float param2;
uniform float param3;
uniform float oparam0;
uniform float oparam1;
uniform float oparam2;
uniform float oparam3;
varying float edge_alpha;

void main(){
 gl_FragColor = texture2D(tex0,varCoord.xy);
 gl_FragColor.a = oparam0 * edge_alpha; 
}