attribute highp   vec3 a_Position;
attribute highp vec3 a_Normal;
attribute mediump vec2 a_TextureCoordinate;
attribute highp vec3 a_Tangent;
attribute highp vec3 a_Binormal;
attribute mediump float a_Color;

uniform highp   mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;

varying highp vec3 _reflectDir;
varying mediump vec2 _varCoord;
varying highp vec3 _viewDirection;

varying highp vec3 _normal;
varying highp vec3 _tangent;
varying highp vec3 _binormal;

varying mediump float _vertexColor;

uniform mediump float time;
uniform mediump float param0;
uniform mediump float param1;
uniform mediump float param2;
uniform mediump float param3;
uniform mediump float oparam0;
uniform mediump float oparam1;
uniform mediump float oparam2;
uniform mediump float oparam3;

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	_varCoord = -a_TextureCoordinate.st;
	
	_viewDirection = normalize(EyePosModel - a_Position);
	
	_normal = a_Normal;
	_tangent = a_Tangent;
	_binormal = a_Binormal;
	
	
	highp vec3 eyeDir = normalize(a_Position - EyePosModel);
	_reflectDir = normalize(ModelWorld * reflect(eyeDir, a_Normal));

	_vertexColor = a_Color;
}
