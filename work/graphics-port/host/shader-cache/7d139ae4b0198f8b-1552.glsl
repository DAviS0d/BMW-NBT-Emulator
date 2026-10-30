precision mediump float;

uniform sampler2D tex0,tex1,tex2,tex3;
varying vec3 ReflectDir;
varying vec2 varCoord;
uniform float time;
uniform float param0,param1,param2,param3;
uniform float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying float n_dot_e;

#define RGB(r,g,b) vec3(r/255., g/255., b/255.)

/*
oparam0 = alpha
oparam1 = reflectivity
oparam2 = color red on
*/


void main(){


 //BASE COLOR
 vec3 base_color = RGB(100., 100., 100.) * n_dot_e;

 gl_FragColor.rgb = base_color;
 gl_FragColor.a = oparam0;
 
}