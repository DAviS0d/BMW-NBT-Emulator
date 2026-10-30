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
uniform float oparam4;
uniform float oparam5;
varying float edge_alpha;

void main(){
	
 vec3 color = vec3(0.5, 0.5, 0.5);	
 float factor = smoothstep(0.0, 1.0, fract(varCoord.x+oparam1) );
 vec4 final_color = mix(vec4(color.rgb, 0.0), vec4(color.rgb, 1.0), factor);

 gl_FragColor = oparam0 * vec4 (final_color.rgb, final_color.a * edge_alpha);
}