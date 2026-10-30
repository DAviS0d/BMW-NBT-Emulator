uniform sampler2D tex0,tex1,tex2,tex3;
varying mediump vec3 ReflectDir;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying mediump float n_dot_e;

void main(){
 gl_FragColor = texture2D(tex0,varCoord.xy ); 
  gl_FragColor.a *= oparam0 * n_dot_e *varCoord.y;
 
}