attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp   mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec3 ReflectDir;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying mediump float n_dot_e;

void main(){
 gl_Position = MVPMatrix * vec4(a_Position, 1.0);
 varCoord = a_TextureCoordinate.st;
 mediump vec3 eyeDir = normalize(a_Position - EyePosModel);
 ReflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal));
  n_dot_e = clamp((1.0 - dot(eyeDir, a_Normal)), 0.,1.) + .4;    //bottom transparency
}
