precision highp float;

precision mediump float;
uniform mat4  	u_transformMatrix;
uniform int 	direction;
uniform float 	scale;
uniform float 	shift;
uniform vec4	u_position2DImage;
uniform vec4	u_texcoord2DImage;

uniform int rotateImage;

attribute vec4 a_Position;
attribute vec2 a_TextureCoordinate;

varying mediump vec2 vTexCoord;

void main()
{
    float sinAngle = sin(float(direction) * radians(90.));
    float cosAngle = cos(float(direction) * radians(90.));

	vTexCoord = a_TextureCoordinate * u_texcoord2DImage.zw + u_texcoord2DImage.xy;
	vec2 vTexCoordFlipped = vec2(vTexCoord.x, 1.0-vTexCoord.y);
   
	mediump vec2 vTexCoordRotated = vec2(
		0.5 + cosAngle*(vTexCoordFlipped.x-0.5) - sinAngle*(vTexCoordFlipped.y - 0.5),
		0.5 + sinAngle*(vTexCoordFlipped.x-0.5) + cosAngle*(vTexCoordFlipped.y - 0.5));

	float scaleFactor = 0.0;
	if(scale<=1.0)
	{
		scaleFactor = scale + (vTexCoord.y)*(1.0-scale);
	}else{
		float s = 1.0/scale;
		scaleFactor = s + (1.0-vTexCoord.y)*(1.0-s);
	}

	if(rotateImage!=0)
	{
		vTexCoord = vTexCoordRotated;
	}
    
	vec2 pos = vec2(0.0,0.0);
	if(shift >= 0.0)
	{
		pos = a_Position.xy * vec2( u_position2DImage.z - shift, u_position2DImage.w ) + u_position2DImage.xy + vec2(shift * a_Position.y, 0.0);
	}else{
		pos = a_Position.xy * vec2( u_position2DImage.z + shift, u_position2DImage.w ) + u_position2DImage.xy + vec2(-shift * (1.0 - a_Position.y), 0.0);
	}
    vec4 transPos = u_transformMatrix * vec4(pos.xy, 0.0, 1.0);
    transPos /= transPos.w;
    transPos = vec4(transPos.xy, a_Position.z, 1.);

	transPos.z *= 1./scaleFactor;
	transPos.w *= 1./scaleFactor;
    gl_Position = transPos;

 /*   vTexCoord = a_TextureCoordinate;
    vec4 transPos = u_transformMatrix * vec4(pos.xy, 0.0, 1.0);
    transPos /= transPos.w;
    gl_Position = vec4(transPos.xy, a_Position.z, 1.);*/
}