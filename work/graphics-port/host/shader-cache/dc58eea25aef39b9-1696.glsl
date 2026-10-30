precision mediump float;

uniform sampler2D tex0;
uniform sampler2D tex1;
uniform sampler2D tex2;
uniform sampler2D tex3;
varying vec3 ReflectDir;
varying vec2 varCoord;
varying vec2 varCoord1;
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
varying float edge_alpha;

void main(){	
	
 vec4 base_color = texture2D(tex0, varCoord.yx);
 gl_FragColor.rgb = base_color.rgb;
 gl_FragColor.a = oparam0 * edge_alpha;
}









/* vec4 base_color = texture2D(tex0, varCoord1.yx);//vec3(0.99,0.40,0.10);
 vec3 glow_color = vec3(0.5,0.0,0.0);
 
 float glow_switch = step(varCoord.y, 0.5);
 //vec3 final_color = mix(glow_color, base_color, glow_switch);

 gl_FragColor = base_color;
 gl_FragColor.a = varCoord.x; //oparam0 * vec4(final_color.rgb, varCoord.x); */