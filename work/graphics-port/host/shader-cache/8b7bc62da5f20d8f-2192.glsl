precision highp float ;
attribute mediump vec2 a_TextureCoordinate,a_TextureCoordinate1;
attribute mediump vec3 a_Position;
uniform highp   mat4 MVPMatrix;
varying mediump vec2 varCoord, varCoord_flipped, varCoord1;

void main()
{
	gl_Position = MVPMatrix * vec4(a_Position, 1.0);

	varCoord = a_TextureCoordinate.st;
	varCoord_flipped = vec2( varCoord.x, 1. - varCoord.y);
	varCoord1 = a_TextureCoordinate1.st;
}
