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
 //divisions	
 vec2 coord_scale = varCoord.xy;
 coord_scale.x = fract (coord_scale.x * 1.5 +0.4975);
 vec4 measure_scale = texture2D(tex0, coord_scale);
  
 gl_FragColor = measure_scale;
 gl_FragColor.a = oparam0 * edge_alpha;
} 