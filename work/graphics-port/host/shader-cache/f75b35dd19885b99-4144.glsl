precision highp float;

attribute mediump float a_Color;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position,a_Normal,a_Tangent,a_Binormal;
uniform highp mat4 MVPMatrix;
uniform mediump mat3 ModelWorld;
uniform mediump vec3 EyePosModel;
uniform mediump vec3 LightPosModel;
varying mediump vec2 varCoord,content_coords,alphaCoord;
uniform mediump float time;
uniform mediump float param0,param1,param2,param3;
uniform mediump float oparam0,oparam1,oparam2,oparam3,oparam4,oparam5,oparam6,oparam7;
varying mediump vec4 varBasicFade;


void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);
	//gl_Position.x += oparam5 * a_Color;
	#define _mirror(A, B) (1.-step(A,B))

	/* texture coords for mirrored repeat */
	varCoord = a_TextureCoordinate.st;
	vec2 mirrored_coords = varCoord;
	mirrored_coords.y = 2.0 * abs(_mirror( mirrored_coords.y, 0.5 ) - mirrored_coords.y);
	varCoord = mirrored_coords;
	
	/* coords for content channel 1280x480 */
	content_coords = a_TextureCoordinate1.st;
	content_coords.x *= oparam7;
	content_coords.y = 1.- content_coords.y;

	float alphaLength = 1./(oparam3 - oparam2);
	alphaCoord = vec2((content_coords.x - oparam2) * alphaLength, 0.);
	varBasicFade = vec4(vec3(oparam6 * oparam0), oparam0);
}
