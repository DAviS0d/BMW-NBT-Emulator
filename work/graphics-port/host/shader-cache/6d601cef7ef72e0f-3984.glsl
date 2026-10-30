precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec2 varCoord,varCoord1;
varying mediump vec3 co;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;


void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	varCoord = a_TextureCoordinate.st;
	float light_width = 0.6;
	varCoord1 = a_TextureCoordinate1.st * light_width;
	float light_translation = oparam2 - 0.5;
	varCoord1.x += light_translation;

	co = mix(vec3(1.,1.,1.), vec3(0.95, 1.1, 1.1), oparam1);   
}
