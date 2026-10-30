attribute highp   vec3 a_Position;
attribute mediump float a_VertexColor;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec2 a_TextureCoordinate1;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;
uniform highp   mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec3 ReflectDir;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0;
uniform mediump float param1;
uniform mediump float param2;
uniform mediump float param3;
uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3;
uniform mediump float oparam4;
uniform mediump float oparam5;
uniform mediump float oparam6;
uniform mediump float oparam7;

void main(){
 gl_Position = MVPMatrix * vec4(a_Position, 1.0);
 varCoord = ( vec2(a_TextureCoordinate.s - 0.5, a_TextureCoordinate.t - 0.5) )
 				 * 2. * oparam1;
 varCoord = (varCoord + vec2(1., 1.)) / 2.;
 mediump vec3 eyeDir = normalize(a_Position - EyePosModel);
 ReflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal));
}
