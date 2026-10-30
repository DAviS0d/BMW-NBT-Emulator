precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec2 varCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;

void main()
{
	vec3 t_pos = a_Position;
	gl_Position = MVPMatrix * vec4(t_pos, 1.0);

  	/**** icon coords ***************/
	varCoord = a_TextureCoordinate.st;
	varCoord *= vec2(oparam6, oparam7);
	varCoord += vec2(oparam4, oparam5);
}