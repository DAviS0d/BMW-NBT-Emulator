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
uniform float oparam6;
uniform float oparam7;

varying float edge_alpha;


void main(){
 //gl_FragColor.a *= oparam2;
  //BASIC COLOR
 vec4 base_color_switch = vec4(	(varCoord.y-oparam1), 		//oparam1 for red amount
 						        (varCoord.y-oparam2), 		//oparam2 for green amount
 						        (varCoord.y-oparam3), 		//oparam3 for blue amount
 						        1.0);
 //OUTLINES
 float darken_factor = 0.2;
 float white_edge = varCoord.x - darken_factor;
 vec4 highlight = vec4(white_edge, white_edge, white_edge, varCoord.x);
 
 
 gl_FragColor.rgb = base_color_switch.rgb + highlight.rgb;
 gl_FragColor.a = edge_alpha;
 gl_FragColor.a *= oparam0;
 gl_FragColor.rgb *= oparam4*(texture2D(tex2,gl_FragCoord.yx*vec2(1./-480.,1./1280.))).rgb; 
}