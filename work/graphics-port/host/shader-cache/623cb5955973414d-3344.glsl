attribute highp   vec3 a_Position;
attribute mediump vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute mediump vec3 a_Tangent;
attribute mediump vec3 a_Binormal;
attribute mediump float a_Color;
uniform highp   mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
uniform mediump float time;
uniform mediump float param0;
uniform mediump float param1;
uniform mediump float param2;
uniform mediump float param3;
uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3;
void main(){
 gl_Position = MVPMatrix * vec4(a_Position, 1.0);
}