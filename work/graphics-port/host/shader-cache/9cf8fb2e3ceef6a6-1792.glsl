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

 /********* for growth **********************************/
 float cutaway_color = varCoord.x + (clamp(oparam1, 0.0,1.0));
 cutaway_color = step(1.0,cutaway_color);
 
 float offset = 0.1;
 float cutaway_object = varCoord.x + (clamp((oparam1+offset),0.0,1.0+offset));
 cutaway_object = step(1.0, cutaway_object);
 
 vec2 coord_scale = varCoord.xy;
 coord_scale.x = fract (coord_scale.x  +0.9975);
 vec4 measure_scale = cutaway_color * texture2D(tex0, coord_scale);
 
 vec2 coord_highlight = varCoord.xy;
 coord_highlight.x *= 4.0;
 coord_highlight.x -= ((1.-oparam1 )* 4.0 - offset);
 vec4 highlight = texture2D(tex1, coord_highlight);
 
 gl_FragColor = measure_scale + highlight;
 gl_FragColor.a = oparam0 * (edge_alpha * cutaway_object * highlight.a) ;  
} 




